# ruff: noqa: F811
"""Mudança 2 (parte A) sobre os arquivos REAIS de producao (handlers.py f7b07719 + messaging.py 5b72aae2, com o patch aplicado).

SQLite real; so o gateway, o orquestrador e o LLM sao substituidos. Prova: eco antes da gravacao nao vira "humano"; pausa de 30 min quando uma
pessoa atua (Twin, Loja, B2B, Azusa, pipeline); descarte se uma pessoa escreve DURANTE a geracao; audio suspeito e dado de contato inventado nao
saem. NAO prova o comportamento no Postgres de producao nem com o Evolution real."""
import sys
import types
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import jobs.handlers as handlers
import providers.llm.factory as llm_factory
from models.contact import Contact
from models.job import Job
from models.message import Message, MessageDirection, MessageMediaType
from services import messaging
from utils.config import get_settings

NOW = datetime.now(timezone.utc)
IN, OUT = MessageDirection.INBOUND, MessageDirection.OUTBOUND
PERSONAL, STORE = "pessoal-teste", "MARQUESCOLOR"


class Reached(Exception):
    pass


@pytest.fixture
async def w(db_engine, monkeypatch):
    settings = get_settings()
    for name, value in dict(
        evolution_personal_instance=PERSONAL, evolution_instance=STORE, whatsapp_twin_mode_enabled=True, auto_reply_enabled=True,
        store_whatsapp_enabled=True, whatsapp_owner_alert_phone="5511900000099", auto_reply_max_message_age_seconds=0,
    ).items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.delenv("HUMAN_PAUSE_MINUTES", raising=False)

    async def owner(self):
        return SimpleNamespace(id=1)

    monkeypatch.setattr("repositories.user.UserRepository.get_first_admin", owner)
    stub = types.ModuleType("services.store_aftercare")
    stub.is_stop_request = lambda _c: False
    stub.stop_followups = None
    monkeypatch.setitem(sys.modules, "services.store_aftercare", stub)
    sales = types.ModuleType("services.store_sales")
    sales.confirmation_code = lambda _c: None
    sales.confirm_quote = None
    monkeypatch.setitem(sys.modules, "services.store_sales", sales)

    class World:
        pass

    world = World()
    world.sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    world.sent, world.calls, world.n = [], [], 0

    class FakeProvider:
        async def send_text(self, to, content, *, instance=None):
            world.sent.append((to, content, instance))
            return {"key": {"id": world.next_id}}

    world.next_id = "WA-1"
    monkeypatch.setattr(handlers, "get_whatsapp_provider", lambda: FakeProvider())
    return world


async def _contact(w, phone):
    async with w.sessions() as db:
        c = Contact(name="Cliente", phone=phone, preferences={}, awaiting_reply_since=NOW)
        db.add(c)
        await db.commit()
        return c.id


async def _msg(w, cid, direction, content, *, instance, minutes_ago=1, human=False, auto=False, media=MessageMediaType.TEXT, ext=None):
    async with w.sessions() as db:
        m = Message(contact_id=cid, direction=direction, media_type=media, content=content, whatsapp_instance=instance,
                    sent_by_human=human, is_autopilot_reply=auto, external_id=ext, created_at=NOW - timedelta(minutes=minutes_ago))
        db.add(m)
        await db.commit()
        return m.id


async def _jobs(w, name="whatsapp.send_text"):
    async with w.sessions() as db:
        return list((await db.scalars(select(Job).where(Job.name == name).order_by(Job.id))).all())


async def _rows(w, cid):
    async with w.sessions() as db:
        return list((await db.scalars(select(Message).where(Message.contact_id == cid).order_by(Message.id))).all())


# ---------------------------------------------------------------- eco antes da gravacao (autoria)
async def test_eco_que_chegou_antes_da_gravacao_e_corrigido_para_o_app_e_nao_duplica(w):
    cid = await _contact(w, "5511900000001")
    await _msg(w, cid, OUT, "Tem sim, vem buscar.", instance=STORE, human=True, ext="WA-1")   # o eco entrou como "humano"
    async with w.sessions() as db:
        await handlers.send_whatsapp_text(db, {"to": "5511900000001", "content": "Tem sim, vem buscar.", "instance": STORE, "is_autopilot_reply": True})
    rows = await _rows(w, cid)
    assert len(rows) == 1 and (rows[0].sent_by_human, rows[0].is_autopilot_reply, rows[0].external_id) == (False, True, "WA-1")


async def test_ordem_normal_grava_uma_linha_com_o_id_do_whatsapp(w):
    cid = await _contact(w, "5511900000002")
    async with w.sessions() as db:
        await handlers.send_whatsapp_text(db, {"to": "5511900000002", "content": "Oi", "instance": STORE})
    (row,) = await _rows(w, cid)
    assert (row.external_id, row.sent_by_human, row.is_autopilot_reply) == ("WA-1", False, False)


async def test_corrida_entre_a_checagem_e_a_gravacao_tambem_corrige(w, monkeypatch):
    cid = await _contact(w, "5511900000003")
    await _msg(w, cid, OUT, "Oi", instance=STORE, human=True, ext="WA-1")
    real, calls = messaging._claim_echo_row, []

    async def first_misses(db, contact_id, external_id, is_autopilot_reply):
        calls.append(1)
        return None if len(calls) == 1 else await real(db, contact_id, external_id, is_autopilot_reply)

    monkeypatch.setattr(messaging, "_claim_echo_row", first_misses)
    async with w.sessions() as db:
        await handlers.send_whatsapp_text(db, {"to": "5511900000003", "content": "Oi", "instance": STORE})
    (row,) = await _rows(w, cid)
    assert (row.sent_by_human, row.external_id) == (False, "WA-1") and len(calls) == 2


async def test_mensagem_humana_de_verdade_com_outro_id_nao_e_tocada(w):
    cid = await _contact(w, "5511900000004")
    await _msg(w, cid, OUT, "Já te falo", instance=STORE, human=True, ext="HUMAN-9")
    async with w.sessions() as db:
        await handlers.send_whatsapp_text(db, {"to": "5511900000004", "content": "Oi", "instance": STORE})
    rows = await _rows(w, cid)
    assert [(r.external_id, r.sent_by_human) for r in rows] == [("HUMAN-9", True), ("WA-1", False)]


# ---------------------------------------------------------------- pausa quando uma pessoa atua
async def test_pessoa_atuou_ha_10_min_pausa_e_ha_40_min_nao(w):
    cid = await _contact(w, "5511900000005")
    await _msg(w, cid, OUT, "oi", instance=STORE, human=True, minutes_ago=40)
    async with w.sessions() as db:
        assert not await handlers._human_active_recently(db, cid, STORE)
    await _msg(w, cid, OUT, "já vejo", instance=STORE, human=True, minutes_ago=10)
    async with w.sessions() as db:
        assert await handlers._human_active_recently(db, cid, STORE)
        assert not await handlers._human_active_recently(db, cid, "b2b-sales")       # isolamento por instancia


async def test_apresentacao_do_robo_gravada_como_humana_nao_conta(w):
    cid = await _contact(w, "5511900000006")
    for text in ("Oi! Aqui é o assistente automático do Dário — ele viu sua mensagem", "Aqui é a Chroma, da Oficina das Tintas", "Aqui é o Twin, assistente do Dário."):
        await _msg(w, cid, OUT, text, instance=STORE, human=True, minutes_ago=2)
    async with w.sessions() as db:
        assert not await handlers._human_active_recently(db, cid, STORE)


async def test_variavel_de_ambiente_muda_a_janela_e_zero_desliga(w, monkeypatch):
    cid = await _contact(w, "5511900000007")
    await _msg(w, cid, OUT, "já vejo", instance=STORE, human=True, minutes_ago=10)
    monkeypatch.setenv("HUMAN_PAUSE_MINUTES", "5")
    async with w.sessions() as db:
        assert not await handlers._human_active_recently(db, cid, STORE)
    monkeypatch.setenv("HUMAN_PAUSE_MINUTES", "0")
    async with w.sessions() as db:
        assert not await handlers._human_active_recently(db, cid, STORE)
    monkeypatch.setenv("HUMAN_PAUSE_MINUTES", "lixo")
    async with w.sessions() as db:
        assert await handlers._human_active_recently(db, cid, STORE)                  # valor invalido volta ao padrao de 30


async def test_arquivo_sobrepoe_a_variavel_e_permite_ligar_e_desligar_sem_reiniciar(w, monkeypatch, tmp_path):
    cid = await _contact(w, "5511900000008")
    await _msg(w, cid, OUT, "já vejo", instance=STORE, human=True, minutes_ago=10)
    arquivo = tmp_path / "pausa.txt"
    monkeypatch.setenv("HUMAN_PAUSE_FILE", str(arquivo))
    async with w.sessions() as db:
        assert await handlers._human_active_recently(db, cid, STORE)                  # sem arquivo: padrao de 30 min
    arquivo.write_text("0\n")
    async with w.sessions() as db:
        assert not await handlers._human_active_recently(db, cid, STORE)              # desligada na hora
    arquivo.write_text("30")
    async with w.sessions() as db:
        assert await handlers._human_active_recently(db, cid, STORE)
    arquivo.write_text("lixo")
    async with w.sessions() as db:
        assert await handlers._human_active_recently(db, cid, STORE)                  # invalido: volta ao padrao


async def _inbound(w, phone, text, instance, *, media=MessageMediaType.TEXT):
    cid = await _contact(w, phone)
    mid = await _msg(w, cid, IN, text, instance=instance, minutes_ago=0.2, media=media)
    return cid, mid


async def _run_process(w, cid, mid, instance):
    async with w.sessions() as db:
        await handlers.process_inbound_whatsapp_message(db, {"contact_id": cid, "message_id": mid, "instance": instance})


@pytest.fixture
def agent(w, monkeypatch):
    calls = []

    async def fake_run(**kwargs):
        calls.append(kwargs)
        from agents.executor import AgentResult
        return AgentResult(reply="Tem sim.")

    monkeypatch.setattr("orchestrator.service.ai_orchestrator.run", fake_run)

    async def pipeline(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(reply="Pipeline ok")

    monkeypatch.setattr("orchestrator.pipeline.cognitive_pipeline.process", pipeline)
    w.calls = calls
    return w


@pytest.mark.parametrize("instance, phone", [(STORE, "5511900000010"), ("b2b-sales", "5511900000011"), ("azusa-church", "5511900000012")])
async def test_agentes_nao_agem_com_pessoa_atuando_e_agem_sem_ela(agent, instance, phone):
    cid, mid = await _inbound(agent, phone, "Tem tinta branca?", instance)
    await _msg(agent, cid, OUT, "Já vejo isso", instance=instance, human=True, minutes_ago=5)
    await _run_process(agent, cid, mid, instance)
    assert agent.calls == [] and await _jobs(agent) == []
    cid2, mid2 = await _inbound(agent, phone[:-1] + "9", "Tem tinta branca?", instance)
    await _run_process(agent, cid2, mid2, instance)
    (call,) = agent.calls
    (job,) = await _jobs(agent)
    assert job.payload["content"] == "Tem sim." and job.payload["_guard_contact_id"] == cid2 and job.payload["_guard_started_at"]


async def test_pipeline_geral_tambem_respeita_a_pausa(agent, monkeypatch):
    monkeypatch.setattr(get_settings(), "store_whatsapp_enabled", False)
    cid, mid = await _inbound(agent, "5511900000013", "Oi", "outra-instancia")
    await _msg(agent, cid, OUT, "já vejo", instance="outra-instancia", human=True, minutes_ago=3)
    await _run_process(agent, cid, mid, "outra-instancia")
    assert agent.calls == []


async def test_loja_com_audio_de_transcricao_inventada_fica_em_silencio_com_registro(agent):
    cid, mid = await _inbound(agent, "5511900000014", "Obrigado por assistir. Legendas pela comunidade Amara.org", STORE, media=MessageMediaType.AUDIO)
    await _run_process(agent, cid, mid, STORE)
    assert agent.calls == [] and await _jobs(agent) == []
    async with agent.sessions() as db:
        from models.log import LogEntry
        logs = list((await db.scalars(select(LogEntry).where(LogEntry.source == "audio_suspeito"))).all())
    assert len(logs) == 1


# ---------------------------------------------------------------- descarte se uma pessoa escreve DURANTE a geracao
async def test_envio_e_descartado_se_uma_pessoa_escreveu_depois_do_inicio_da_geracao(w):
    cid = await _contact(w, "5511900000015")
    started = (NOW - timedelta(minutes=2)).isoformat()
    await _msg(w, cid, OUT, "pode deixar que eu respondo", instance=STORE, human=True, minutes_ago=1)
    payload = {"to": "5511900000015", "content": "Tem sim.", "instance": STORE, "_guard_contact_id": cid, "_guard_started_at": started}
    async with w.sessions() as db:
        await handlers.send_whatsapp_text(db, payload)
    assert w.sent == [] and [r.content for r in await _rows(w, cid)] == ["pode deixar que eu respondo"]
    await _msg(w, cid, OUT, "ok", instance=STORE, human=True, minutes_ago=30)           # antes do inicio da geracao nao conta
    async with w.sessions() as db:
        await handlers.send_whatsapp_text(db, {**payload, "_guard_started_at": (NOW + timedelta(minutes=1)).isoformat()})
    assert len(w.sent) == 1


async def test_envio_sem_marca_de_guarda_segue_como_antes(w):
    cid = await _contact(w, "5511900000016")
    await _msg(w, cid, OUT, "oi", instance=STORE, human=True, minutes_ago=1)
    async with w.sessions() as db:
        await handlers.send_whatsapp_text(db, {"to": "5511900000016", "content": "Alerta", "instance": STORE})
    assert len(w.sent) == 1


# ---------------------------------------------------------------- Twin
@pytest.fixture
def twin(w, monkeypatch):
    async def fake_chat(messages, tools=None):
        return SimpleNamespace(content="x")

    monkeypatch.setattr(llm_factory, "chat_with_fallback", fake_chat, raising=False)
    import agents.darius_twin as darius_twin

    box = SimpleNamespace(reply="Vou sim.", calls=0)
    # O portao de risco de PRODUCAO (orchestrator/twin_risk_gate.py) nao esta nesta copia; a assinatura dele e (mensagem, historico) -> (risco, motivo).
    monkeypatch.setattr("orchestrator.twin_risk_gate.is_high_risk_for_impersonation", lambda message, history: (False, ""))

    async def fake_generate(history, message, *, contact_name=""):
        box.calls += 1
        return box.reply

    monkeypatch.setattr(darius_twin, "generate_darius_reply", fake_generate)
    w.box = box
    return w


async def _twin_inbound(w, phone, text, *, media=MessageMediaType.TEXT):
    cid, mid = await _inbound(w, phone, text, PERSONAL, media=media)
    return cid, mid


async def _run_twin(w, cid, mid):
    async with w.sessions() as db:
        await handlers.twin_autopilot_check(db, {"contact_id": cid, "message_id": mid, "instance": PERSONAL})


async def test_twin_responde_quando_ninguem_atua(twin):
    cid, mid = await _twin_inbound(twin, "5511900000020", "Vai hoje?")
    await _run_twin(twin, cid, mid)
    (job,) = await _jobs(twin)
    assert job.payload["content"] == "Vou sim." and job.payload["_guard_contact_id"] == cid and twin.box.calls == 1


async def test_twin_fica_em_silencio_3_minutos_depois_de_o_dono_responder_o_caso_brittany(twin):
    cid, mid = await _twin_inbound(twin, "5511900000021", "Hummmmk")
    await _msg(twin, cid, OUT, "Ah, eu estou testando ainda", instance=PERSONAL, human=True, minutes_ago=3, media=MessageMediaType.AUDIO)
    await _run_twin(twin, cid, mid)
    assert twin.box.calls == 0 and await _jobs(twin) == []


async def test_twin_audio_curto_vira_alerta_ao_dono_e_nao_resposta(twin):
    cid, mid = await _twin_inbound(twin, "5511900000022", "Paz pastor", media=MessageMediaType.AUDIO)
    await _run_twin(twin, cid, mid)
    jobs = await _jobs(twin)
    assert twin.box.calls == 0 and [j.payload["to"] for j in jobs] == ["5511900000099"] and "transcrição pouco confiável" in jobs[0].payload["content"]


async def test_twin_resposta_com_email_inventado_nao_sai_e_com_o_email_do_dono_sai(twin):
    cid, mid = await _twin_inbound(twin, "5511900000023", "Me passa seu e-mail?")
    twin.box.reply = "Bom dia! dariomarques@outlook.com"
    await _run_twin(twin, cid, mid)
    jobs = await _jobs(twin)
    assert [j.payload["to"] for j in jobs] == ["5511900000099"] and "dado de contato não verificável" in jobs[0].payload["content"]
    cid2, mid2 = await _twin_inbound(twin, "5511900000024", "Me passa seu e-mail?")
    twin.box.reply = "Pode ser: dariomneto@hotmail.com"
    await _run_twin(twin, cid2, mid2)
    assert [j.payload["to"] for j in await _jobs(twin)][-1] == "5511900000024"


async def test_twin_email_que_o_proprio_contato_escreveu_pode_ser_repetido(twin):
    cid, mid = await _twin_inbound(twin, "5511900000025", "Manda pro meu e-mail joao@exemplo.com por favor")
    twin.box.reply = "Combinado, mando para joao@exemplo.com"
    await _run_twin(twin, cid, mid)
    assert [j.payload["to"] for j in await _jobs(twin)] == ["5511900000025"]


def test_detectores_puros():
    assert handlers._audio_transcript_unreliable("Devemos outro bem.", min_words=5)
    assert not handlers._audio_transcript_unreliable("Devemos outro bem.", min_words=0)
    assert handlers._audio_transcript_unreliable("sim sim sim sim sim sim", min_words=0)
    assert handlers._audio_transcript_unreliable("", min_words=0)
    assert handlers._unverified_contact_data("Liga 11 91234-5678", []) == "telefone_ou_documento"
    assert handlers._unverified_contact_data("Fala no (11) 98258-9350", ["meu zap 11982589350"]) is None
    assert handlers._unverified_contact_data("Veja https://loja.exemplo.com/x.", ["https://loja.exemplo.com/x"]) is None
