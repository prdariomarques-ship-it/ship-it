# ruff: noqa: F811
"""Regressões do parecer de 12/10/2026 sobre o vendedor ativo e a voz da Marquescolor.

Cada teste usa o worker e os handlers REAIS (só o transporte WhatsApp e o serviço de voz são simulados) e afirma ZERO chamadas
ao provedor quando o envio deve ser bloqueado. Dados fictícios. Os testes de concorrência real (duas sessões, PostgreSQL)
estão em tests/test_followup_claim_postgres.py.
"""
import asyncio
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select, text

import jobs.handlers  # noqa: F401
from jobs.service import JobService
from jobs.worker import JobWorker
from models.contact import Contact
from models.job import Job
from models.message import Message, MessageDirection, MessageMediaType
from models.store_voice import StoreVoiceSend
from services import store_followups as sf, store_hours, store_optout, store_voice, voice_client
from tests import test_store_voice as tv
from tests.test_store_followups import (  # noqa: F401 -- fixtures e ajudantes reutilizados
    NOW, PHONE, STORE, add_customer, add_products, add_quote, all_followups, env, plan, planned, run,
)
from utils.config import Settings, get_settings


async def drain(rounds=8):
    for _ in range(rounds):
        if not await JobWorker().run_once():
            break


async def queued_followup(env):
    """Acompanhamento planejado e JÁ ENFILEIRADO (job criado, ainda não executado)."""
    cid, kid, qid = await planned(env)
    (entry,) = await run(env, apply=True)
    assert entry["action"] == "queued"
    return cid, kid, qid, entry["job_id"]


# =====================================================================================================================
# P1 — o job de acompanhamento já enfileirado revalida TUDO imediatamente antes do transporte
# =====================================================================================================================
async def _inbound(env, kid, content):
    async with env.sessions() as db:
        contact = await db.get(Contact, kid)
        msg = Message(contact_id=kid, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content=content,
                      whatsapp_instance=STORE, created_at=NOW - timedelta(minutes=1))
        db.add(msg)
        await db.flush()
        reply = await store_optout.handle_inbound(db, contact, msg)
        await db.commit()
        return reply


async def test_parar_depois_de_enfileirar_nao_transmite(env):
    cid, kid, qid, job_id = await queued_followup(env)
    assert await _inbound(env, kid, "PARAR") == store_optout.ACK_OPTOUT
    await drain()
    assert env.text.calls == []                                # zero chamadas ao provedor
    (fu,) = await all_followups(env)
    assert fu.status == "cancelled" and "não receber" in fu.cancel_reason and fu.history[-1]["event"] == "cancelled_before_send"
    async with env.sessions() as db:
        assert (await db.get(Job, job_id)).status.value == "succeeded"
        n = (await db.execute(text("SELECT count(*) FROM conversation_send_intents"))).scalar()
        assert n == 0                                          # nada foi reservado: não há envio incerto a conciliar


async def test_recusa_depois_de_enfileirar_nao_transmite(env):
    cid, kid, qid, _ = await queued_followup(env)
    await _inbound(env, kid, "não tenho interesse")
    await drain()
    assert env.text.calls == []
    assert (await all_followups(env))[0].status == "cancelled"


async def test_preferencia_por_texto_depois_de_enfileirar_ainda_envia_o_texto(env):
    """Controle negativo: preferir texto é preferência de FORMATO, não recusa; o acompanhamento escrito continua autorizado."""
    cid, kid, qid, _ = await queued_followup(env)
    async with env.sessions() as db:
        contact = await db.get(Contact, kid)
        contact.preferences = {"reply_mode": "texto", "voice_opt_out": True}
        await db.commit()
    await drain()
    assert len(env.text.calls) == 1


async def test_chave_desligada_depois_de_enfileirar_adia_sem_gastar_tentativa(env, monkeypatch):
    cid, kid, qid, _ = await queued_followup(env)
    monkeypatch.setattr(env.s, "store_followups_enabled", False)
    await drain()
    assert env.text.calls == []
    (fu,) = await all_followups(env)
    assert (fu.status, fu.attempts, fu.job_id) == ("scheduled", 0, None) and fu.history[-1]["event"] == "deferred_disabled"
    # religada, o mesmo acompanhamento volta a sair — uma vez, com novo job
    monkeypatch.setattr(env.s, "store_followups_enabled", True)
    async with env.sessions() as db:
        await sf.run_due(db, now=fu.due_at + timedelta(seconds=1), apply=True)
    await drain()
    assert len(env.text.calls) == 1


async def test_horario_deixou_de_ser_confirmado_depois_de_enfileirar(env, monkeypatch):
    cid, kid, qid, _ = await queued_followup(env)
    monkeypatch.setattr(env.s, "store_hours_confirmed", False)
    await drain()
    assert env.text.calls == []
    assert (await all_followups(env))[0].history[-1]["event"] == "deferred_hours_unconfirmed"


@pytest.mark.parametrize("hhmm_utc, motivo", [
    ((20, 5), "fora da janela"),      # 17:05 BRT: enfileirado às 16:59, executado depois da margem de fechamento
    ((22, 0), "fora da janela"),      # 19:00 BRT: loja fechada
    ((14, 59), None),                 # 11:59 BRT: ainda dentro (controle negativo)
])
async def test_envio_fora_da_janela_depois_de_esperar_na_fila(env, monkeypatch, hhmm_utc, motivo):
    cid, kid, qid, _ = await queued_followup(env)
    agora = datetime(2026, 10, 6, *hhmm_utc, tzinfo=timezone.utc)
    monkeypatch.setattr(sf, "_now", lambda: agora)
    # a conversa do cliente é anterior a 'agora' em todos os casos; só o relógio muda
    await drain()
    (fu,) = await all_followups(env)
    if motivo:
        assert env.text.calls == [] and fu.status == "scheduled" and fu.attempts == 0 and fu.history[-1]["event"] == "deferred_window"
        assert fu.due_at.replace(tzinfo=timezone.utc) > agora          # adiado para a próxima abertura
    else:
        assert len(env.text.calls) == 1


async def test_texto_desatualizado_pelo_estoque_nao_e_enviado(env):
    cid, kid, qid, _ = await queued_followup(env)
    async with env.sessions() as db:
        from models.product import Product
        p = (await db.scalars(select(Product).where(Product.sku == "TL18"))).one()
        p.stock_quantity = 0
        await db.commit()
    await drain()
    assert env.text.calls == []
    assert (await all_followups(env))[0].status == "cancelled"


async def test_humano_assumiu_depois_de_enfileirar(env):
    cid, kid, qid, _ = await queued_followup(env)
    async with env.sessions() as db:
        db.add(Message(contact_id=kid, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType.TEXT, content="oi, é a equipe",
                       sent_by_human=True, whatsapp_instance=STORE, created_at=NOW - timedelta(minutes=1)))
        await db.commit()
    await drain()
    assert env.text.calls == []


async def test_job_alheio_ou_acompanhamento_inexistente_nao_transmite(env):
    cid, kid, qid, job_id = await queued_followup(env)
    async with env.sessions() as db:                           # um segundo job (identidade diferente) para o MESMO acompanhamento
        payload = dict((await db.get(Job, job_id)).payload)
        await JobService(db).enqueue("whatsapp.send_text", payload)
        await JobService(db).enqueue("whatsapp.send_text", {"to": PHONE, "content": "oi", "instance": STORE, "followup_id": 9999, "followup_attempt": 1})
    await drain()
    assert len(env.text.calls) == 1                            # só o job dono transmite; o impostor e o inexistente são barrados


async def test_guard_so_libera_o_job_dono_do_acompanhamento(env):
    cid, kid, qid, job_id = await queued_followup(env)
    async with env.sessions() as db:
        payload = dict((await db.get(Job, job_id)).payload)
        assert await sf.send_guard(db, {**payload, "_job_id": job_id}) is None
        assert "não está pendente" in await sf.send_guard(db, {**payload, "_job_id": job_id + 1})
        assert "não está pendente" in await sf.send_guard(db, {k: v for k, v in payload.items()})        # sem _job_id
        assert "tentativa" in await sf.send_guard(db, {**payload, "_job_id": job_id, "followup_attempt": 2})


async def test_acompanhamento_sem_identidade_de_job_falha_fechado(env):
    from jobs.handlers import send_whatsapp_text
    async with env.sessions() as db:
        await send_whatsapp_text(db, {"to": PHONE, "content": "oi", "instance": STORE, "followup_id": 1})   # sem _job_id
    assert env.text.calls == []


async def test_resultado_ambiguo_continua_sem_reenvio_e_com_identidade_estavel(env, monkeypatch):
    class Timeout(tv.TextTransport):
        async def send_text(self, to, content, instance=None):
            self.calls.append((to, content, instance))
            e = Exception("evolution request failed: ReadTimeout")
            e.__cause__ = httpx.ReadTimeout("sem resposta")
            raise e
    t = Timeout()
    monkeypatch.setattr("jobs.handlers.get_whatsapp_provider", lambda: t)
    cid, kid, qid, _ = await queued_followup(env)
    await drain(10)
    assert len(t.calls) == 1
    async with env.sessions() as db:
        ids = [r[0] for r in (await db.execute(text("SELECT id FROM conversation_send_intents"))).all()]
    assert ids == [sf.send_intent_id(1, 1)]                    # a reserva é do ACOMPANHAMENTO, não só do job


async def test_voz_do_acompanhamento_obedece_a_mesma_decisao(env, monkeypatch):
    monkeypatch.setattr(env.s, "store_voice_enabled", True)
    monkeypatch.setattr(env.s, "store_voice_url", "http://voice.test")
    monkeypatch.setattr(env.s, "store_voice_token", "t" * 40)
    await add_products(env)
    cid, kid = await add_customer(env, prefs={"reply_mode": "audio"})
    await add_quote(env, cid, kid)
    await plan(env, apply=True)
    await run(env, apply=True)
    fechada = datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc)                  # 18:00 BRT
    # o texto sai dentro da janela; quando a voz vai gerar (depois do texto), a loja já fechou
    monkeypatch.setattr(sf, "_now", lambda: NOW if not env.text.calls else fechada)
    await drain()
    assert len(env.text.calls) == 1
    async with env.sessions() as db:
        (v,) = (await db.scalars(select(StoreVoiceSend))).all()
    assert v.status == "cancelled" and "horário de atendimento" in v.reason and env.voice.calls == []


async def test_voz_do_acompanhamento_com_opt_out_posterior_nao_fala(env, monkeypatch):
    monkeypatch.setattr(env.s, "store_voice_enabled", True)
    monkeypatch.setattr(env.s, "store_voice_url", "http://voice.test")
    monkeypatch.setattr(env.s, "store_voice_token", "t" * 40)
    await add_products(env)
    cid, kid = await add_customer(env, prefs={"reply_mode": "audio"})
    await add_quote(env, cid, kid)
    await plan(env, apply=True)
    await run(env, apply=True)

    async def customer_stops():
        await _inbound(env, kid, "PARAR")
    env.synth.before = customer_stops
    await drain()
    async with env.sessions() as db:
        (v,) = (await db.scalars(select(StoreVoiceSend))).all()
    assert v.status == "cancelled" and env.voice.calls == []


# =====================================================================================================================
# P1 — claim atômico por acompanhamento (a prova com duas sessões em PostgreSQL está no outro arquivo)
# =====================================================================================================================
async def test_dois_processadores_geram_um_unico_job(env):
    await planned(env)
    r1, r2 = await asyncio.gather(run(env, apply=True), run(env, apply=True))
    actions = sorted(e["action"] for e in r1 + r2)
    assert actions.count("queued") == 1
    async with env.sessions() as db:
        jobs = (await db.scalars(select(Job).where(Job.name == "whatsapp.send_text"))).all()
        assert len(jobs) == 1
    await drain()
    assert len(env.text.calls) == 1


async def test_claim_perdido_nao_cria_job(env, monkeypatch):
    """O perdedor da corrida (outro processador já tomou a linha entre a seleção e o claim) não cria job."""
    await planned(env)
    original = sf._revalidate
    taken = []

    async def revalidate_then_lose(db, fu, now, s):
        out = await original(db, fu, now, s)
        if not taken:
            taken.append(True)
            async with env.sessions() as other:                # o outro processador assume antes do nosso claim
                await sf.run_due(other, now=NOW, apply=True)
        return out
    monkeypatch.setattr(sf, "_revalidate", revalidate_then_lose)
    (entry,) = await run(env, apply=True)
    assert entry["action"] == "skip" and "outro processador" in entry["reason"]
    async with env.sessions() as db:
        assert len((await db.scalars(select(Job).where(Job.name == "whatsapp.send_text"))).all()) == 1


# =====================================================================================================================
# P2 — pedido afirmativo de áudio não é recusa de áudio
# =====================================================================================================================
@pytest.mark.parametrize("texto, esperado", [
    ("quero áudio", "audio_request"), ("mande áudio", "audio_request"), ("me manda áudio", "audio_request"),
    ("Pode mandar um áudio?", "audio_request"), ("por favor envie áudio", "audio_request"), ("prefiro áudio", "audio_request"),
    ("não quero áudio", "text_only"), ("não mande áudio", "text_only"), ("nao me manda audio", "text_only"),
    ("quero áudio não", "text_only"), ("mande áudio não", "text_only"), ("só texto", "text_only"), ("sem áudio", "text_only"),
])
def test_classificacao_audio_positivo_e_negativo(texto, esperado):
    assert store_optout.classify(texto) == esperado


async def _inbound_handler(env, content, prefs, phone):
    async with env.sessions() as db:
        contact = Contact(name="Cliente", phone=phone, preferences=prefs)
        db.add(contact)
        await db.flush()
        msg = Message(contact_id=contact.id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content=content,
                      whatsapp_instance=STORE)
        db.add(msg)
        await db.commit()
        return contact.id, msg.id


async def test_pedido_de_audio_passa_pelo_handler_real_sem_virar_recusa(env, monkeypatch):
    from jobs.handlers import process_inbound_whatsapp_message

    class Reached(Exception):
        pass

    def stop_check(_content):
        raise Reached                                          # primeiro ponto DEPOIS da interceptação de preferência

    import sys
    import types
    stub = types.ModuleType("services.store_aftercare")        # o módulo de pós-venda real não faz parte desta linha de código
    stub.is_stop_request = stop_check                          # type: ignore[attr-defined]
    stub.stop_followups = None                                 # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "services.store_aftercare", stub)
    monkeypatch.setattr("repositories.user.UserRepository.get_first_admin", _fake_owner)

    casos = [
        ("quero áudio", {}, False, True),
        ("mande áudio", {"reply_mode": "texto", "voice_opt_out": True}, False, True),     # reverte um 'só texto' anterior
        ("não quero áudio", {}, True, False),
    ]
    for i, (frase, prefs_antes, voz_depois, chegou_ao_agente) in enumerate(casos):
        phone = f"551199999{i:04d}"
        cid, mid = await _inbound_handler(env, frase, dict(prefs_antes), phone)
        async with env.sessions() as db:
            if chegou_ao_agente:
                with pytest.raises(Reached):
                    await process_inbound_whatsapp_message(db, {"contact_id": cid, "message_id": mid, "instance": STORE})
            else:
                await process_inbound_whatsapp_message(db, {"contact_id": cid, "message_id": mid, "instance": STORE})
        async with env.sessions() as db:
            prefs = (await db.get(Contact, cid)).preferences
            jobs = [j for j in (await db.scalars(select(Job).where(Job.name == "whatsapp.send_text"))).all() if j.payload["to"] == phone]
        assert bool(prefs.get("voice_opt_out")) is voz_depois
        assert "store_contact_opt_out" not in prefs and "store_followup_paused_until" not in prefs
        if chegou_ao_agente:
            assert prefs["reply_mode"] == "audio" and jobs == []            # sem interceptação nem confirmação
        else:
            assert prefs["reply_mode"] == "texto" and [j.payload["content"] for j in jobs] == [store_optout.ACK_TEXT_ONLY]


async def _fake_owner(self):
    class U:
        id = 1
    return U()


async def test_pedido_de_audio_nao_reverte_opt_out_de_contatos(env):
    async with env.sessions() as db:
        c = Contact(name="C", phone=PHONE, preferences={"store_contact_opt_out": True, "store_followup_opt_out": True})
        db.add(c)
        await db.flush()
        m = Message(contact_id=c.id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content="mande áudio", whatsapp_instance=STORE)
        db.add(m)
        await db.flush()
        assert await store_optout.handle_inbound(db, c, m) is None
        assert c.preferences["reply_mode"] == "audio" and c.preferences["store_contact_opt_out"] is True
        assert store_optout.is_blocked(c) == "cliente pediu para não receber contatos"


# =====================================================================================================================
# P2 — o roteiro FINAL cabe no limite do serviço de voz
# =====================================================================================================================
SERVICE_LIMIT = 350
REPORT_REPLY = " ".join(["Esta é uma frase de apresentação simples."] * 5) + "\nPreço R$ 10,00"


def _service_default_max_text() -> int:
    spec = importlib.util.spec_from_file_location("voice_service_config", Path(__file__).resolve().parents[2] / "voice-service" / "app" / "config.py")
    try:
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return int(module.VoiceSettings.model_fields["max_text_chars"].default)
    except Exception:   # noqa: BLE001 -- dependências do serviço ausentes neste ambiente
        pytest.skip("voice-service/app/config.py não pôde ser carregado aqui")


def test_limite_do_backend_nao_passa_do_limite_do_servico():
    assert Settings(_env_file=None).store_voice_max_script_chars <= _service_default_max_text() == SERVICE_LIMIT


@pytest.mark.parametrize("reply, disclose", [
    (REPORT_REPLY, True),                                      # o exemplo do parecer: 422 caracteres antes da correção
    (REPORT_REPLY, False),
    (" ".join(["Temos todas as cores disponíveis para pronta entrega."] * 12), True),
    ("Claro! " * 60, True),
    ("Posso ajudar. Itens:\n- 2 x Tinta R$ 450,00", True),
    ("Olá! " + "x" * 600, True),
])
def test_roteiro_final_cabe_no_limite_e_mantem_a_identificacao(reply, disclose):
    script = store_voice.build_script(reply, disclose=disclose, max_chars=Settings(_env_file=None).store_voice_max_script_chars)
    assert script is not None and len(script) <= SERVICE_LIMIT
    if disclose:
        assert script.startswith(store_voice.DISCLOSURE)         # o aviso de voz sintética NUNCA é removido para caber
    assert not any(ch.isdigit() for ch in script) and "R$" not in script


def test_exemplo_do_parecer_tinha_422_e_agora_tem_o_aviso_o_resumo_e_o_ponteiro():
    script = store_voice.build_script(REPORT_REPLY, disclose=True, max_chars=340)
    assert store_voice.DISCLOSURE in script and script.endswith(store_voice.POINTER) and len(script) <= 340
    assert "frase de apresentação" in script                   # o resumo encolheu, não sumiu


def test_nenhum_tamanho_de_resposta_ultrapassa_o_limite():
    for n in range(0, 80):
        reply = " ".join(["Frase curta de teste número."] * n) + ("\nTotal: R$ 9,90" if n % 2 else "")
        for disclose in (True, False):
            script = store_voice.build_script(reply, disclose=disclose, max_chars=340)
            assert script is None or len(script) <= 340


def test_limite_tao_pequeno_que_nao_cabe_o_aviso_nao_gera_audio():
    assert store_voice.build_script("Olá, posso ajudar.", disclose=True, max_chars=50) is None


# =====================================================================================================================
# Download do áudio com limite durante a leitura
# =====================================================================================================================
def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://voice.test")


@pytest.fixture
def voice_cfg(monkeypatch):
    s = get_settings()
    for k, v in dict(store_voice_url="http://voice.test", store_voice_token="t" * 40, store_voice_max_audio_bytes=1000).items():
        monkeypatch.setattr(s, k, v)
    return s


def _meta(body: bytes):
    return {"audio_id": "A1", "sha256": hashlib.sha256(body).hexdigest(), "duration_seconds": 1.0, "engine": "e", "model_revision": "r", "reference_sha256": "x"}


async def test_audio_acima_do_limite_com_content_length_e_recusado_sem_baixar(voice_cfg):
    consumed = []

    async def body():
        for _ in range(100):
            consumed.append(1)
            yield b"x" * 100

    def handler(req):
        if req.method == "POST":
            return httpx.Response(200, json=_meta(b""))
        return httpx.Response(200, headers={"content-length": "10000"}, content=body())
    with pytest.raises(voice_client.VoiceRejected) as e:
        await voice_client.synthesize("Olá, tudo bem?", "store-voice-1", client=_client(handler))
    assert e.value.code == "too_large" and len(consumed) <= 1


async def test_audio_acima_do_limite_sem_content_length_para_a_leitura_no_limite(voice_cfg):
    consumed = []

    async def body():
        for _ in range(1000):
            consumed.append(1)
            yield b"x" * 100

    def handler(req):
        if req.method == "POST":
            return httpx.Response(200, json=_meta(b""))
        return httpx.Response(200, content=body())              # transferência em pedaços: sem Content-Length
    with pytest.raises(voice_client.VoiceRejected) as e:
        await voice_client.synthesize("Olá, tudo bem?", "store-voice-1", client=_client(handler))
    assert e.value.code == "too_large" and len(consumed) <= 12   # parou perto do limite (1000 B), não leu 100 kB


async def test_resposta_de_metadados_gigante_e_recusada(voice_cfg):
    def handler(req):
        return httpx.Response(200, content=b"{" + b" " * (200 * 1024) + b"}")
    with pytest.raises(voice_client.VoiceRejected) as e:
        await voice_client.synthesize("Olá, tudo bem?", "store-voice-1", client=_client(handler))
    assert e.value.code == "too_large"


async def test_audio_dentro_do_limite_continua_funcionando(voice_cfg):
    data = b"OggS" + b"x" * 500

    def handler(req):
        if req.method == "POST":
            return httpx.Response(200, json=_meta(data))
        if req.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, content=data)
    audio = await voice_client.synthesize("Olá, tudo bem?", "store-voice-1", client=_client(handler))
    assert audio.data == data


# =====================================================================================================================
# P2 — horário: confirmação pendente, margem, consulta por data, fuso
# =====================================================================================================================
def cfg(**kw):
    return Settings(_env_file=None, **kw)


def test_padrao_nao_e_confirmado():
    assert cfg().store_hours_confirmed is False


def test_descricao_sem_confirmacao_e_qualificada():
    assert store_hours.describe(cfg()).startswith("Horário informado, ainda NÃO confirmado pela equipe da loja:")
    assert not store_hours.describe(cfg(store_hours_confirmed=True)).startswith("Horário informado")


async def _tool(s, monkeypatch, **args):
    from agents.tools.base import ToolContext
    from agents.tools.domain import get_store_hours_tool
    monkeypatch.setattr("agents.tools.domain.get_settings", lambda: s)
    return json.loads(await get_store_hours_tool.handler(ToolContext(db=None, user=None, contact_id=None), **args))   # type: ignore[arg-type]


async def test_ferramenta_com_configuracao_padrao_responde_qualificado_e_sem_afirmar_aberto(monkeypatch):
    out = await _tool(cfg(), monkeypatch)
    assert out["horario_confirmado_pela_equipe"] is False and "NÃO foi confirmado" in out["aviso_obrigatorio"]
    assert out["aberto_agora"] is None and "aberto_agora_segundo_o_horario_informado" in out
    out = await _tool(cfg(), monkeypatch, date="2026-10-07")
    assert "aviso_obrigatorio" in out and out["horario_do_dia"] == "08:30–17:30"


async def test_ferramenta_confirmada_nao_traz_aviso(monkeypatch):
    out = await _tool(cfg(store_hours_confirmed=True), monkeypatch)
    assert "aviso_obrigatorio" not in out and isinstance(out["aberto_agora"], bool)


async def test_consulta_por_data_nao_inventa_um_agora(monkeypatch):
    out = await _tool(cfg(store_hours_confirmed=True), monkeypatch, date="2026-10-07")
    assert "aberto_agora" not in out and "instante_avaliado" not in out and out["horario_do_dia"] == "08:30–17:30"


def test_agora_usa_o_instante_real_e_nao_meio_dia():
    s = cfg(store_hours_confirmed=True)
    tarde = datetime(2026, 10, 7, 21, 0, tzinfo=timezone.utc)                 # quarta 18:00 BRT: fechada
    assert store_hours.status_at(tarde, s)["aberto_agora"] is False
    assert store_hours.day_info(tarde.date(), s).get("aberto_agora") is None  # o horário do dia não diz nada sobre 'agora'


def test_prompt_manda_informar_horario_nao_confirmado():
    from agents.store_agent import StoreAgent
    assert "aviso_obrigatorio" in StoreAgent().system_prompt


@pytest.mark.parametrize("margem", [-1, -30, 241])
def test_margem_invalida_derruba_a_carga(margem):
    with pytest.raises(ValidationError, match="store_followup_close_margin_minutes"):
        cfg(store_followup_close_margin_minutes=margem)


@pytest.mark.parametrize("margem", [0, 30, 240])
def test_margem_valida_e_aceita(margem):
    assert cfg(store_followup_close_margin_minutes=margem).store_followup_close_margin_minutes == margem


def test_limite_da_janela_com_a_margem_nao_pode_ser_estendido():
    s = cfg(store_hours_confirmed=True)
    fim = datetime(2026, 10, 7, 20, 45, tzinfo=timezone.utc)                  # 17:45 BRT, loja fecha 17:30
    assert sf.in_window(fim, s) is False
    assert store_hours.is_open(fim, s, close_margin=timedelta(0)) is False


@pytest.mark.parametrize("fuso", ["Marte/Olimpo", "", "America/Nao_Existe"])
def test_fuso_desconhecido_derruba_a_carga(fuso):
    with pytest.raises(ValidationError, match="store_timezone"):
        cfg(store_timezone=fuso)


def test_fuso_valido_e_aceito():
    assert cfg(store_timezone="America/Sao_Paulo").store_timezone == "America/Sao_Paulo"


async def test_sem_confirmacao_nao_se_planeja_nem_se_aplica_acompanhamento(env, monkeypatch):
    monkeypatch.setattr(env.s, "store_hours_confirmed", False)
    await add_products(env)
    cid, kid = await add_customer(env)
    await add_quote(env, cid, kid)
    (entry,) = await plan(env, apply=True)
    assert entry["action"] == "skip" and "não confirmado" in entry["reason"]
    assert await all_followups(env) == []
    with pytest.raises(sf.FollowupsDisabled):
        await run(env, apply=True)
