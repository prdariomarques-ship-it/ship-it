"""As edições ancoradas de docs/vendedor-ativo/owner-guard aplicadas ao TEXTO REAL de produção (fixture com as funções colhidas da VPS em
18/10/2026) e EXECUTADAS: banco real (SQLite de teste), serviço owner_activity real; só o transporte, o LLM e os repositórios de leitura
do fixture são simulados. Prova o comportamento dos 3 agentes, a revalidação no envio e o roteamento de alerta ao dono."""
import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.contact import Contact
from models.log import LogEntry
from models.message import Message, MessageDirection, MessageMediaType
from providers.whatsapp.evolution.provider import EvolutionProvider
from services import line_watch
from services import owner_activity as oa
from utils.config import get_settings

GUARD_DIR = Path(__file__).resolve().parents[2] / "docs" / "vendedor-ativo" / "owner-guard"
PHONE_CLIENT, PHONE_OWNER = "5511988887777", "5511993366903"


def _load_patched():
    spec = importlib.util.spec_from_file_location("aplicar_owner_guard", GUARD_DIR / "aplicar_owner_guard.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    source = gen.build((GUARD_DIR / "prod_fixture_handlers.py").read_text(encoding="utf-8"))
    return source, gen


class _Provider(EvolutionProvider):
    def __init__(self):
        super().__init__()
        self.sent: list[tuple] = []

    async def send_text(self, to, content, instance=None):
        self.sent.append((to, content, instance))
        return {"key": {"id": "X"}}


@pytest.fixture
async def world(db_engine, tmp_path, monkeypatch):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(oa, "WINDOWS_FILE", str(tmp_path / "janelas.txt"))
    s = get_settings()
    for name, value in dict(auto_reply_enabled=True, store_whatsapp_enabled=True, evolution_personal_instance="Dario",
                            evolution_instance="MARQUESCOLOR", line_watch_alert_phone=PHONE_OWNER).items():
        monkeypatch.setattr(s, name, value)
    line_watch.line_watch_state.reset()

    w = types.SimpleNamespace(sessions=sessions, provider=_Provider(), enqueued=[], persisted=[], llm_calls=[], contact_id=None, msg_id=None)
    async with sessions() as db:
        c = Contact(name="Cliente", phone=PHONE_CLIENT, preferences={})
        db.add(c)
        await db.flush()
        m = Message(contact_id=c.id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content="quanto custa?",
                    whatsapp_instance="b2b-sales", created_at=datetime.now(timezone.utc))
        db.add(m)
        await db.commit()
        w.contact_id, w.msg_id = c.id, m.id

    # --- ambiente do fixture
    class Repo:
        def __init__(self, db): self.db = db
    class ContactRepository(Repo):
        async def get(self, cid): return types.SimpleNamespace(id=cid, phone=PHONE_CLIENT)
    class MessageRepository(Repo):
        async def get(self, mid):
            async with sessions() as db:
                return await db.get(Message, mid)
        async def recent_for_contact(self, cid, limit=20, instance=None): return []
    class UserRepository(Repo):
        async def get_first_admin(self): return types.SimpleNamespace(id=1)
    class JobService(Repo):
        async def enqueue(self, name, payload=None, **kw): w.enqueued.append((name, payload))
    async def persist_outbound_message(db, to, content, is_autopilot_reply=False, instance=None): w.persisted.append((to, content, instance))
    async def audio_guard(db, payload, to, instance): return True

    source, gen = _load_patched()
    ns = {"__name__": "handlers_fixture", "ContactRepository": ContactRepository, "MessageRepository": MessageRepository,
          "UserRepository": UserRepository, "JobService": JobService, "persist_outbound_message": persist_outbound_message,
          "_owner_audio_send_guard": audio_guard, "get_whatsapp_provider": lambda: w.provider,
          "logger": types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)}
    exec(compile(source, "handlers_patched.py", "exec"), ns)
    w.send, w.process, w.source = ns["send_whatsapp_text"], ns["process_inbound_whatsapp_message"], source

    # --- LLM e módulos de produção que o repositório não tem
    async def fake_run(**kwargs):
        w.llm_calls.append(kwargs.get("agent_name"))
        return types.SimpleNamespace(reply="Resposta do agente.")
    from orchestrator.service import ai_orchestrator
    monkeypatch.setattr(ai_orchestrator, "run", fake_run)
    hist = types.ModuleType("services.extra_agent_history")
    hist.build_extra_agent_history = lambda recent, message: []
    monkeypatch.setitem(sys.modules, "services.extra_agent_history", hist)
    aftercare = types.ModuleType("services.store_aftercare")
    aftercare.is_stop_request = lambda text: False
    async def stop_followups(db, contact): return None
    aftercare.stop_followups = stop_followups
    monkeypatch.setitem(sys.modules, "services.store_aftercare", aftercare)
    sales = types.ModuleType("services.store_sales")
    sales.confirmation_code = lambda text: None
    async def confirm_quote(db, contact_id, code): raise ValueError("sem orçamento")
    sales.confirm_quote = confirm_quote
    monkeypatch.setitem(sys.modules, "services.store_sales", sales)
    w.sales = sales
    return w


async def _owner_turn(w, *, media="AUDIO", seconds_ago=40, instance="b2b-sales"):
    at = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    async with w.sessions() as db:
        m = Message(contact_id=w.contact_id, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType[media], content="",
                    whatsapp_instance=instance, sent_by_human=True, is_autopilot_reply=False, created_at=at, provider_timestamp=at)
        db.add(m)
        await db.commit()
        return m.id


async def _guard_logs(w):
    async with w.sessions() as db:
        return [l.payload for l in (await db.execute(select(LogEntry).where(LogEntry.source == "owner_activity_guard"))).scalars().all()]


async def _inbound(w, instance):
    async with w.sessions() as db:
        m = await db.get(Message, w.msg_id)
        m.whatsapp_instance = instance
        await db.commit()
    async with w.sessions() as db:
        await w.process(db, {"contact_id": w.contact_id, "message_id": w.msg_id, "instance": instance})


# ------------------------------------------------------------------ B2B / Azusa
@pytest.mark.parametrize("instance,agent", [("b2b-sales", "b2b"), ("azusa-church", "azusa_intake")])
async def test_extra_agents_stay_silent_while_the_owner_is_active_and_log_the_event(world, instance, agent):
    owner_msg = await _owner_turn(world, media="AUDIO", instance=instance)                       # áudio do dono, como no contato 154
    await _inbound(world, instance)
    assert world.llm_calls == [] and world.enqueued == []                                         # nem gerou nem enfileirou
    (event,) = await _guard_logs(world)
    assert event["event"] == "suppressed_owner_active" and event["agent"] == agent and event["phase"] == "pre"
    assert event["owner_message_id"] == owner_msg and event["window_seconds"] == 180 and event["contact_id"] == world.contact_id


@pytest.mark.parametrize("instance", ["b2b-sales", "azusa-church"])
async def test_extra_agents_answer_when_the_owner_is_not_active_and_mark_the_send(world, instance):
    await _owner_turn(world, seconds_ago=900, instance=instance)                                 # dono falou há 15 min
    await _inbound(world, instance)
    assert world.llm_calls != []
    ((name, payload),) = world.enqueued
    assert name == "whatsapp.send_text" and payload["to"] == PHONE_CLIENT and payload["instance"] == instance
    assert payload["_owner_guard"] in ("b2b", "azusa_intake") and payload["_owner_guard_contact_id"] == world.contact_id
    assert await _guard_logs(world) == []


# ------------------------------------------------------------------ loja
async def test_store_agent_silent_while_owner_active_and_answers_otherwise(world):
    await _owner_turn(world, media="PDF", instance="MARQUESCOLOR")
    await _inbound(world, "MARQUESCOLOR")
    assert world.llm_calls == [] and world.enqueued == []
    assert (await _guard_logs(world))[0]["agent"] == "store"
    async with world.sessions() as db:
        await db.execute(Message.__table__.delete().where(Message.sent_by_human.is_(True)))
        await db.commit()
    await _inbound(world, "MARQUESCOLOR")
    ((_, payload),) = world.enqueued
    assert world.llm_calls == ["store"] and payload["_owner_guard"] == "store" and payload["instance"] == "MARQUESCOLOR"


async def test_store_order_confirmation_is_never_blocked_nor_marked(world, monkeypatch):
    """Confirmação de pedido tem efeito real (cria o pedido): continua mesmo com o dono ativo, e a resposta fixa não é revalidada."""
    world.sales.confirmation_code = lambda text: "ABC123"

    async def fake_confirm(db, contact_id, code):
        return {"order": {"total": "10.50"}}
    world.sales.confirm_quote = fake_confirm
    await _owner_turn(world, instance="MARQUESCOLOR")
    await _inbound(world, "MARQUESCOLOR")
    ((_, payload),) = world.enqueued
    assert "Pedido ABC123 registrado" in payload["content"] and "_owner_guard" not in payload and world.llm_calls == []


async def test_personal_instance_path_is_untouched(world, monkeypatch):
    await _owner_turn(world, instance="Dario")
    from orchestrator import pipeline

    async def fake_process(**kwargs):
        return types.SimpleNamespace(reply="resposta da pipeline")
    monkeypatch.setattr(pipeline.cognitive_pipeline, "process", fake_process)
    await _inbound(world, "Dario")
    ((_, payload),) = world.enqueued
    assert payload["content"] == "resposta da pipeline" and "_owner_guard" not in payload and await _guard_logs(world) == []


# ------------------------------------------------------------------ envio (revalidação) e alerta ao dono
async def test_send_revalidates_and_catches_the_owner_who_arrived_during_generation(world):
    payload = {"to": PHONE_CLIENT, "content": "Resposta do agente.", "instance": "b2b-sales", **oa.guard_payload("b2b", world.contact_id, world.msg_id)}
    async with world.sessions() as db:
        await world.send(db, dict(payload))
    assert world.provider.sent == [(PHONE_CLIENT, "Resposta do agente.", "b2b-sales")]            # dono inativo: sai
    await _owner_turn(world, media="AUDIO", seconds_ago=5)                                        # entra durante a geração
    async with world.sessions() as db:
        await world.send(db, dict(payload))
    assert len(world.provider.sent) == 1 and len(world.persisted) == 1                            # barrado: nada transmitido nem gravado
    assert (await _guard_logs(world))[-1]["phase"] == "send"


async def test_send_without_the_mark_is_never_blocked(world):
    await _owner_turn(world, seconds_ago=5)
    async with world.sessions() as db:
        await world.send(db, {"to": PHONE_CLIENT, "content": "enviado pelo painel", "instance": "b2b-sales"})
    assert len(world.provider.sent) == 1


async def test_owner_alert_goes_through_another_open_line_when_the_store_is_down(world):
    line_watch.record_states({"MARQUESCOLOR": "connecting", "b2b-sales": "open", "Dario": "open"})
    async with world.sessions() as db:
        await world.send(db, {"to": "+55 (11) 99336-6903", "content": "[Gêmeo Darius] Mensagem sensível ..."})
    assert world.provider.sent == [("+55 (11) 99336-6903", "[Gêmeo Darius] Mensagem sensível ...", "b2b-sales")]
    assert world.persisted[0][2] == "b2b-sales"                                                   # gravado na linha que realmente enviou
    async with world.sessions() as db:                                                             # cliente comum: nunca redirecionado
        await world.send(db, {"to": PHONE_CLIENT, "content": "oi"})
    assert world.provider.sent[-1][2] is None
    line_watch.record_states({"MARQUESCOLOR": "open", "b2b-sales": "open"})                       # loja no ar: alerta segue pela padrão
    async with world.sessions() as db:
        await world.send(db, {"to": PHONE_OWNER, "content": "alerta 2"})
    assert world.provider.sent[-1][2] is None


def test_patched_source_is_valid_python_with_all_six_edits():
    source, _ = _load_patched()
    compile(source, "x", "exec")
    for needle in ("_lw.route_owner_alert", "_oa.send_guard", "_oa.pre_check(db, extra_agents[instance]", "_oa.guard_payload(extra_agents[instance]",
                   '_oa.pre_check(db, "store"', "**_guard_extra"):
        assert needle in source, needle
