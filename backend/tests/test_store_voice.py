"""Resposta por voz do vendedor da loja, ponta a ponta pelo worker REAL e pelos handlers reais.

Só os clientes externos são simulados: o serviço de voz (VoiceAudio com OGG/Opus de fixture sintética) e o transporte
WhatsApp (texto e voz). Banco SQLite isolado por teste; tabelas de controle de conversa criadas pelas migrações reais.
Dados 100% fictícios.
"""
import base64
import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

import jobs.handlers  # noqa: F401 -- registra os handlers
from jobs.service import JobService
from jobs.worker import JobWorker
from models.contact import Contact
from models.job import Job, JobStatus
from models.message import Message, MessageDirection, MessageMediaType
from models.store_voice import StoreVoiceSend
from providers.whatsapp.base import WhatsAppProviderError
from services import conversation_control, store_voice, voice_client
from tests.test_whatsapp_send_queue_retry import _migrate_control_tables_sync
from utils.config import get_settings

PHONE = "5511999990000"
STORE = "MARQUESCOLOR"
PERSONAL = "pessoal-teste"
AUDIO = (Path(__file__).parent / "fixtures" / "voice" / "tone_2s_mono.ogg").read_bytes()
STEREO = (Path(__file__).parent / "fixtures" / "voice" / "tone_1s_stereo.ogg").read_bytes()
REPLY_COM_DETALHES = "Temos sim a tinta que você pediu.\nItens:\n- 2 x Tinta Látex 18L - R$ 450,00\nTotal: R$ 900,00"


class TextTransport:
    name = "evolution"
    default_instance = STORE

    def __init__(self):
        self.calls = []

    async def send_text(self, to, content, instance=None):
        self.calls.append((to, content, instance))
        return {"key": {"id": f"TXT-{len(self.calls)}"}}


class VoiceTransport:
    name = "evolution"
    default_instance = STORE

    def __init__(self, outcomes=None):
        self.calls = []
        self.outcomes = list(outcomes or [])

    async def send_voice(self, to, audio_base64, instance=None):
        self.calls.append((to, audio_base64, instance))
        outcome = self.outcomes.pop(0) if self.outcomes else {"key": {"id": f"VOZ-{len(self.calls)}"}}
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeSynth:
    """Simula voice_client.synthesize; `before` roda durante a geração (o mundo muda enquanto o áudio é feito)."""

    def __init__(self, data=AUDIO, error=None):
        self.data, self.error, self.calls, self.before = data, error, [], None

    async def __call__(self, text, request_id):
        # Contrato REAL do serviço (voice-service/app/service.py): um request_id curto leva 422 em produção. Este simulador o
        # reproduz para que o pipeline não possa passar com um id inválido (bug achado só na demonstração com o serviço real).
        assert re.match(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,63}$", request_id), request_id
        self.calls.append((text, request_id))
        if self.before:
            await self.before()
        if self.error:
            raise self.error
        return voice_client.VoiceAudio(self.data, hashlib.sha256(self.data).hexdigest(), 2.0, "fake-engine", "rev-teste", "r" * 64, "A1")


@pytest_asyncio.fixture
async def env(db_engine, monkeypatch):
    async with db_engine.begin() as conn:
        await conn.run_sync(_migrate_control_tables_sync)
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("jobs.worker.async_session_factory", sessions)
    s = get_settings()
    for key, value in dict(
        store_voice_enabled=True, store_voice_url="http://voice.test", store_voice_token="t" * 40, store_whatsapp_enabled=True,
        auto_reply_enabled=True, evolution_instance=STORE, evolution_personal_instance=PERSONAL, jobs_retry_backoff_seconds=0,
        store_voice_policy="mirror_audio", store_voice_max_per_contact_per_day=3,
    ).items():
        monkeypatch.setattr(s, key, value)
    text_t, voice_t, synth = TextTransport(), VoiceTransport(), FakeSynth()
    monkeypatch.setattr("jobs.handlers.get_whatsapp_provider", lambda: text_t)
    monkeypatch.setattr("services.store_voice.get_whatsapp_provider", lambda: voice_t)
    monkeypatch.setattr(voice_client, "synthesize", synth)

    class Env:
        pass
    e = Env()
    e.sessions, e.text, e.voice, e.synth, e.settings = sessions, text_t, voice_t, synth, s
    return e


async def seed(env, *, media=MessageMediaType.AUDIO, instance=STORE, prefs=None, phone=PHONE, content="Preciso de tinta"):
    async with env.sessions() as db:
        contact = Contact(name="Cliente Teste", phone=phone, preferences=prefs or {})
        db.add(contact)
        await db.flush()
        msg = Message(contact_id=contact.id, direction=MessageDirection.INBOUND, media_type=media, content=content, whatsapp_instance=instance)
        db.add(msg)
        await db.commit()
        return contact.id, msg.id


async def queue_text(env, message_id, *, reply=REPLY_COM_DETALHES, instance=STORE, companion=True, phone=PHONE):
    payload = {"to": phone, "content": reply, "instance": instance}
    if companion:
        payload["voice_companion"] = {"source_message_id": message_id}
    async with env.sessions() as db:
        return (await JobService(db).enqueue("whatsapp.send_text", payload)).id


async def run_all(rounds=6):
    for _ in range(rounds):
        if not await JobWorker().run_once():
            break


async def rows(env):
    async with env.sessions() as db:
        return list((await db.scalars(select(StoreVoiceSend).order_by(StoreVoiceSend.id))).all())


async def jobs_named(env, name):
    async with env.sessions() as db:
        return list((await db.scalars(select(Job).where(Job.name == name))).all())


# ----------------------------------------------------------------------------------------------- funções puras
def test_resumo_falado_nao_tem_numeros_nem_links_e_aponta_para_o_texto():
    spoken, details = store_voice.spoken_summary(REPLY_COM_DETALHES, 300)
    assert spoken == "Temos sim a tinta que você pediu." and details is True
    script = store_voice.build_script(REPLY_COM_DETALHES, disclose=True, max_chars=300)
    assert script.startswith(store_voice.DISCLOSURE) and script.endswith(store_voice.POINTER)
    assert not any(ch.isdigit() for ch in script) and "R$" not in script and "http" not in script


def test_resposta_simples_sem_detalhes_nao_ganha_ponteiro():
    script = store_voice.build_script("Claro! Posso ajudar com a escolha da cor.", disclose=False, max_chars=300)
    assert script == "Claro! Posso ajudar com a escolha da cor."


def test_link_e_codigo_ficam_so_por_escrito():
    spoken, details = store_voice.spoken_summary("Segue o orçamento. Veja https://exemplo.test/x e use o código ABC123XYZ.", 300)
    assert spoken == "Segue o orçamento." and details is True
    assert store_voice.build_script("Preço R$ 10,00", disclose=False, max_chars=300) == store_voice.POINTER


def test_roteiro_respeita_limite_de_caracteres_e_vazio_nao_fala():
    long_reply = " ".join(["Esta é uma frase de apresentação simples."] * 30)
    spoken, details = store_voice.spoken_summary(long_reply, 120)
    assert len(spoken) <= 120 and details is True
    assert store_voice.build_script("   ", disclose=True, max_chars=300) is None


def test_roteiro_nao_afirma_que_o_proprietario_ouviu_ou_respondeu():
    script = store_voice.build_script("Olá, posso ajudar.", disclose=True, max_chars=300).lower()
    assert "assistente virtual" in script and "voz sintética" in script
    for frase in ("eu mesmo", "pessoalmente", "ouvi seu", "vi sua mensagem"):
        assert frase not in script


@pytest.mark.parametrize("prefs, media, policy, expected", [
    ({}, MessageMediaType.AUDIO, "mirror_audio", True),
    ({}, MessageMediaType.TEXT, "mirror_audio", False),
    ({"reply_mode": "audio"}, MessageMediaType.TEXT, "customer_preference", True),
    ({}, MessageMediaType.AUDIO, "customer_preference", False),
    ({"reply_mode": "texto"}, MessageMediaType.AUDIO, "mirror_audio", False),       # preferência por texto sempre vence
    ({"reply_mode": "audio", "voice_opt_out": True}, MessageMediaType.AUDIO, "mirror_audio", False),
])
def test_politica_de_voz(env, monkeypatch, prefs, media, policy, expected):
    monkeypatch.setattr(env.settings, "store_voice_policy", policy)
    contact = Contact(name="x", phone=PHONE, preferences=prefs)
    msg = Message(contact_id=1, direction=MessageDirection.INBOUND, media_type=media, content="x", whatsapp_instance=STORE)
    assert store_voice.decide(contact, msg, env.settings).use_voice is expected


def test_desligado_ou_sem_configuracao_nao_fala(env, monkeypatch):
    contact = Contact(name="x", phone=PHONE, preferences={"reply_mode": "audio"})
    monkeypatch.setattr(env.settings, "store_voice_enabled", False)
    assert store_voice.decide(contact, None, env.settings).reason == "voz desligada"
    monkeypatch.setattr(env.settings, "store_voice_enabled", True)
    monkeypatch.setattr(env.settings, "store_voice_token", "")
    assert store_voice.decide(contact, None, env.settings).reason == "serviço de voz não configurado"


# ----------------------------------------------------------------------------------------------- caminho feliz
async def test_texto_primeiro_depois_voz_curta_pela_instancia_da_loja(env):
    contact_id, mid = await seed(env)
    await queue_text(env, mid)
    await run_all()
    assert len(env.text.calls) == 1 and env.text.calls[0][1] == REPLY_COM_DETALHES   # texto completo, primeiro
    assert len(env.voice.calls) == 1
    to, b64, instance = env.voice.calls[0]
    assert (to, instance) == (PHONE, STORE) and base64.b64decode(b64) == AUDIO
    (row,) = await rows(env)
    assert row.status == "sent" and row.receipt_id == "VOZ-1" and row.audio_sha256 == hashlib.sha256(AUDIO).hexdigest()
    assert row.script_text.startswith(store_voice.DISCLOSURE) and not any(ch.isdigit() for ch in row.script_text)
    assert env.synth.calls[0][0] == row.script_text and env.synth.calls[0][1] == f"store-voice-{row.id}"
    assert [h["event"] for h in row.history] == ["queued", "generating", "sending", "sent"]
    async with env.sessions() as db:
        sent = (await db.scalars(select(Message).where(Message.direction == MessageDirection.OUTBOUND, Message.media_type == MessageMediaType.AUDIO))).all()
        assert len(sent) == 1 and sent[0].external_id == "VOZ-1" and sent[0].is_autopilot_reply and sent[0].whatsapp_instance == STORE
        receipts = (await db.execute(text("SELECT external_id FROM conversation_receipts WHERE contact_id=:c"), {"c": contact_id})).scalars().all()
        assert "VOZ-1" in receipts and "TXT-1" in receipts          # o eco do próprio áudio será reconhecido (não vira "humano")


async def test_aviso_de_voz_sintetica_so_na_primeira_vez_da_semana(env):
    _, mid1 = await seed(env)
    await queue_text(env, mid1)
    await run_all()
    async with env.sessions() as db:
        contact_id = (await db.scalars(select(Contact.id))).first()
        m2 = Message(contact_id=contact_id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.AUDIO, content="outra", whatsapp_instance=STORE)
        db.add(m2)
        await db.commit()
        mid2 = m2.id
    await queue_text(env, mid2, reply="Combinado, até logo.")
    await run_all()
    first, second = await rows(env)
    assert store_voice.DISCLOSURE in first.script_text and store_voice.DISCLOSURE not in second.script_text
    # passada uma semana, o aviso volta
    async with env.sessions() as db:
        await db.execute(update(StoreVoiceSend).where(StoreVoiceSend.id.in_([first.id, second.id])).values(sent_at=datetime.now(timezone.utc) - timedelta(days=8)))
        await db.commit()
    async with env.sessions() as db:
        assert await store_voice._needs_disclosure(db, first.contact_id, STORE, 7) is True


async def test_cliente_que_escreveu_texto_nao_recebe_voz(env):
    _, mid = await seed(env, media=MessageMediaType.TEXT)
    await queue_text(env, mid)
    await run_all()
    assert len(env.text.calls) == 1 and env.voice.calls == [] and await rows(env) == []


async def test_job_de_texto_sem_marca_de_voz_nao_gera_voz(env):
    _, mid = await seed(env)
    await queue_text(env, mid, companion=False)
    await run_all()
    assert len(env.text.calls) == 1 and env.voice.calls == [] and await rows(env) == []


# ----------------------------------------------------------------------------------------------- isolamento de instância
@pytest.mark.parametrize("instance", [PERSONAL, "b2b-sales", "azusa-church", "outra"])
async def test_so_a_instancia_da_loja_pode_ter_voz(env, instance):
    _, mid = await seed(env, instance=instance)
    await queue_text(env, mid, instance=instance)
    await run_all()
    assert env.voice.calls == [] and await rows(env) == [] and await jobs_named(env, "store.voice_reply") == []


async def test_linha_forjada_para_a_instancia_pessoal_e_cancelada_sem_enviar(env):
    contact_id, mid = await seed(env, instance=PERSONAL)
    async with env.sessions() as db:
        row = StoreVoiceSend(dedupe_key="voice:reply:forjado", kind="reply", contact_id=contact_id, instance=PERSONAL,
                             source_message_id=mid, status="queued", script_text="Olá.", history=[])
        db.add(row)
        await db.flush()
        await JobService(db).enqueue("store.voice_reply", {"voice_send_id": row.id}, max_attempts=1)
        await db.commit()
    await run_all()
    (row,) = await rows(env)
    assert row.status == "cancelled" and "instância" in row.reason and env.voice.calls == [] and env.synth.calls == []


# ----------------------------------------------------------------------------------------------- falhas antes do envio
@pytest.mark.parametrize("error, reason", [
    (voice_client.VoiceUnavailable("timeout", "lento"), "serviço de voz: timeout"),
    (voice_client.VoiceUnavailable("busy", "cheio"), "serviço de voz: busy"),
    (voice_client.VoiceUnavailable("engine_not_ready", "sem modelo"), "serviço de voz: engine_not_ready"),
    (voice_client.VoiceRejected("hash_mismatch", "x"), "serviço de voz: hash_mismatch"),
])
async def test_falha_do_gerador_nao_envia_voz_e_o_texto_ja_foi(env, error, reason):
    env.synth.error = error
    _, mid = await seed(env)
    await queue_text(env, mid)
    await run_all()
    (row,) = await rows(env)
    assert row.status == "failed_before_send" and row.reason == reason and env.voice.calls == []
    assert len(env.text.calls) == 1                    # a resposta escrita foi entregue; nada mais é enviado
    assert (await jobs_named(env, "store.voice_reply"))[0].status == JobStatus.SUCCEEDED    # sem retentativa em laço


@pytest.mark.parametrize("data, trecho", [
    (b"RIFF" + b"\0" * 200, "OggS"), (STEREO, "mono"), (AUDIO[:3000], "truncad"), (b"", "tamanho"),
])
async def test_formato_de_audio_invalido_e_barrado_antes_do_envio(env, data, trecho):
    env.synth.data = data
    _, mid = await seed(env)
    await queue_text(env, mid)
    await run_all()
    (row,) = await rows(env)
    assert row.status == "failed_before_send" and "áudio inválido" in row.reason and trecho in row.reason
    assert env.voice.calls == []


async def test_audio_acima_da_duracao_maxima(env, monkeypatch):
    monkeypatch.setattr(env.settings, "store_voice_max_audio_seconds", 1.0)
    _, mid = await seed(env)
    await queue_text(env, mid)
    await run_all()
    (row,) = await rows(env)
    assert row.status == "failed_before_send" and "duração" in row.reason and env.voice.calls == []


# ----------------------------------------------------------------------------------------------- o mundo muda durante a geração
async def test_cliente_responde_durante_a_geracao_cancela_antes_do_envio(env):
    contact_id, mid = await seed(env)

    async def customer_writes():
        async with env.sessions() as db:
            db.add(Message(contact_id=contact_id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT,
                           content="na verdade quero outra cor", whatsapp_instance=STORE))
            await db.commit()
    env.synth.before = customer_writes
    await queue_text(env, mid)
    await run_all()
    (row,) = await rows(env)
    assert row.status == "cancelled" and "cliente respondeu" in row.reason and "após gerar" in row.reason and env.voice.calls == []


async def test_atendimento_humano_assume_durante_a_geracao(env):
    contact_id, mid = await seed(env)

    async def human_takes_over():
        async with env.sessions() as db:
            db.add(Message(contact_id=contact_id, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType.TEXT, content="Oi, sou eu.",
                           whatsapp_instance=STORE, sent_by_human=True))
            await db.commit()
    env.synth.before = human_takes_over
    await queue_text(env, mid)
    await run_all()
    (row,) = await rows(env)
    assert row.status == "cancelled" and "humano" in row.reason and env.voice.calls == []


async def test_pausa_da_conversa_durante_a_geracao(env):
    contact_id, mid = await seed(env)

    async def pause():
        async with env.sessions() as db:
            await conversation_control.pause(db, contact_id, STORE, "evt-1", "teste")
            await db.commit()
    env.synth.before = pause
    await queue_text(env, mid)
    await run_all()
    (row,) = await rows(env)
    assert row.status == "cancelled" and "pausada" in row.reason and env.voice.calls == []


async def test_pausa_antes_de_gerar_nem_chama_o_gerador(env):
    contact_id, mid = await seed(env)
    await queue_text(env, mid)
    # o texto sai; antes do job de voz rodar, a conversa é pausada
    await JobWorker().run_once()
    async with env.sessions() as db:
        await conversation_control.pause(db, contact_id, STORE, "evt-2", "teste")
        await db.commit()
    await run_all()
    (row,) = await rows(env)
    assert row.status == "cancelled" and env.synth.calls == [] and env.voice.calls == []


@pytest.mark.parametrize("prefs", [{"reply_mode": "texto"}, {"voice_opt_out": True}])
async def test_cliente_que_passa_a_preferir_texto_antes_do_envio(env, prefs):
    contact_id, mid = await seed(env)
    await queue_text(env, mid)
    await JobWorker().run_once()
    async with env.sessions() as db:
        c = await db.get(Contact, contact_id)
        c.preferences = prefs
        await db.commit()
    await run_all()
    (row,) = await rows(env)
    assert row.status == "cancelled" and row.reason == "cliente prefere texto" and env.voice.calls == []


async def test_pedido_antigo_demais_e_descartado(env, monkeypatch):
    contact_id, mid = await seed(env)
    await queue_text(env, mid)
    await JobWorker().run_once()
    async with env.sessions() as db:
        await db.execute(update(StoreVoiceSend).values(created_at=datetime.now(timezone.utc) - timedelta(seconds=env.settings.store_voice_max_job_age_seconds + 60)))
        await db.commit()
    await run_all()
    (row,) = await rows(env)
    assert row.status == "cancelled" and "antigo" in row.reason and env.voice.calls == []


async def test_limite_diario_de_audios(env, monkeypatch):
    monkeypatch.setattr(env.settings, "store_voice_max_per_contact_per_day", 1)
    contact_id, mid1 = await seed(env)
    await queue_text(env, mid1)
    await run_all()
    async with env.sessions() as db:
        m2 = Message(contact_id=contact_id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.AUDIO, content="mais uma", whatsapp_instance=STORE)
        db.add(m2)
        await db.commit()
        mid2 = m2.id
    await queue_text(env, mid2, reply="Certo.")
    await run_all()
    first, second = await rows(env)
    assert first.status == "sent" and second.status == "cancelled" and "limite" in second.reason and len(env.voice.calls) == 1


# ----------------------------------------------------------------------------------------------- duplicidade
async def test_dois_pedidos_para_a_mesma_mensagem_geram_uma_voz(env):
    _, mid = await seed(env)
    await queue_text(env, mid)
    await queue_text(env, mid, reply=REPLY_COM_DETALHES + " ")      # segundo job de texto com a mesma origem
    await run_all()
    assert len(await rows(env)) == 1 and len(env.voice.calls) == 1


async def test_reexecutar_o_mesmo_job_de_voz_nao_reenvia(env):
    _, mid = await seed(env)
    await queue_text(env, mid)
    await run_all()
    (row,) = await rows(env)
    async with env.sessions() as db:
        await store_voice.deliver(db, {"voice_send_id": row.id})
        await store_voice.deliver(db, {"voice_send_id": row.id})
    assert len(env.voice.calls) == 1 and len(env.synth.calls) == 1


async def test_geracao_interrompida_vira_falha_segura_ao_reexecutar(env):
    contact_id, mid = await seed(env)
    async with env.sessions() as db:
        row = StoreVoiceSend(dedupe_key="voice:reply:x", kind="reply", contact_id=contact_id, instance=STORE, source_message_id=mid,
                             status="generating", script_text="Olá.", attempts=1, history=[])
        db.add(row)
        await db.commit()
        rid = row.id
    async with env.sessions() as db:
        await store_voice.deliver(db, {"voice_send_id": rid})
    (row,) = await rows(env)
    assert row.status == "failed_before_send" and env.synth.calls == [] and env.voice.calls == []


# ----------------------------------------------------------------------------------------------- transporte
def _ambiguo():
    e = WhatsAppProviderError("evolution request failed: ReadTimeout")
    e.__cause__ = httpx.ReadTimeout("sem resposta")
    return e


def _nao_enviado():
    e = WhatsAppProviderError("evolution request failed: ConnectError")
    e.__cause__ = httpx.ConnectError("recusado")
    return e


async def test_resultado_incerto_nao_repete_e_nao_manda_texto_de_reserva(env):
    env.voice.outcomes = [_ambiguo()]
    _, mid = await seed(env)
    await queue_text(env, mid)
    await run_all()
    (row,) = await rows(env)
    assert row.status == "needs_review" and "incerto" in row.reason and len(env.voice.calls) == 1
    texts_before = list(env.text.calls)
    async with env.sessions() as db:                       # reexecuções (job, reconciliação) não mudam nada
        await store_voice.deliver(db, {"voice_send_id": row.id})
        await store_voice.reconcile_stuck(db, older_than_seconds=0)
    await run_all()
    (row,) = await rows(env)
    assert row.status == "needs_review" and len(env.voice.calls) == 1 and env.text.calls == texts_before
    assert len(texts_before) == 1                          # só o texto original, nenhum "fallback"
    async with env.sessions() as db:                       # a reserva permanece (impede reenvio por qualquer caminho)
        n = (await db.execute(text("SELECT count(*) FROM conversation_send_intents WHERE id=:i"), {"i": f"voice-send:{row.id}"})).scalar()
        assert n == 1


async def test_conexao_recusada_prova_que_nao_enviou_e_libera_a_reserva(env):
    env.voice.outcomes = [_nao_enviado()]
    _, mid = await seed(env)
    await queue_text(env, mid)
    await run_all()
    (row,) = await rows(env)
    assert row.status == "failed_before_send" and "provadamente" in row.reason
    async with env.sessions() as db:
        n = (await db.execute(text("SELECT count(*) FROM conversation_send_intents WHERE id=:i"), {"i": f"voice-send:{row.id}"})).scalar()
        assert n == 0


async def test_aceito_sem_recibo_fica_para_revisao(env):
    env.voice.outcomes = [{"status": "ok"}]
    _, mid = await seed(env)
    await queue_text(env, mid)
    await run_all()
    (row,) = await rows(env)
    assert row.status == "needs_review" and "sem recibo" in row.reason and len(env.voice.calls) == 1 and row.receipt_id is None


async def test_provedor_sem_suporte_a_voz_nao_envia(env, monkeypatch):
    class NoVoice:
        name = "baileys"
    monkeypatch.setattr("services.store_voice.get_whatsapp_provider", lambda: NoVoice())
    _, mid = await seed(env)
    await queue_text(env, mid)
    await run_all()
    (row,) = await rows(env)
    assert row.status == "failed_before_send" and "provedor" in row.reason


async def test_reconciliacao_de_linhas_presas(env):
    contact_id, mid = await seed(env)
    async with env.sessions() as db:
        for key, status in (("a", "generating"), ("b", "sending")):
            db.add(StoreVoiceSend(dedupe_key=f"voice:reply:{key}", kind="reply", contact_id=contact_id, instance=STORE,
                                  source_message_id=mid, status=status, script_text="x", history=[]))
        await db.commit()
    async with env.sessions() as db:
        counts = await store_voice.reconcile_stuck(db, older_than_seconds=0)
    a, b = await rows(env)
    assert counts == {"generating": 1, "sending": 1}
    assert (a.status, b.status) == ("failed_before_send", "needs_review") and env.voice.calls == []


async def test_falha_ao_pedir_a_voz_nao_derruba_o_envio_do_texto(env, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("banco indisponível")
    monkeypatch.setattr(store_voice, "enqueue_reply_companion", boom)
    _, mid = await seed(env)
    jid = await queue_text(env, mid)
    await run_all()
    async with env.sessions() as db:
        assert (await db.get(Job, jid)).status == JobStatus.SUCCEEDED
    assert len(env.text.calls) == 1 and env.voice.calls == []


async def test_marca_de_voz_apontando_para_mensagem_de_outro_contato_ou_de_saida_e_ignorada(env):
    _, mid_a = await seed(env)
    other_contact, mid_b = await seed(env, phone="5511888880000")
    async with env.sessions() as db:
        out = Message(contact_id=other_contact, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType.TEXT, content="x", whatsapp_instance=STORE)
        db.add(out)
        await db.commit()
        out_id = out.id
    await queue_text(env, mid_b)                      # origem de OUTRO contato (a mensagem é do contato 888880000, o envio vai a PHONE)
    await queue_text(env, out_id)                     # origem é mensagem de saída
    await queue_text(env, 99999)                      # origem inexistente
    await run_all()
    assert await rows(env) == [] and env.voice.calls == [] and len(env.text.calls) == 3
