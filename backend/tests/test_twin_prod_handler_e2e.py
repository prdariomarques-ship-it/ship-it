"""twin_autopilot_check DE PRODUCAO (docs/twin-role-inversion/prod/originais/handlers.py), original e patcheado, com banco de teste.

Usa os guardas REAIS de producao enviados em 24/10 (twin_audio_gate, twin_autoreply_gate, twin_commitment_guard, twin_finance_guard). So quatro modulos
de producao que NAO recebi sao substituidos por stubs neutros: orchestrator.twin_policy, orchestrator.twin_output_guard, jobs.owner_audio_dependencies e a assinatura de producao de
orchestrator.twin_risk_gate (devolve (bool, motivo)). Nenhum LLM real; nenhum envio: so se le a fila de jobs.
Prova com codigo real: o original de producao ENVIA "Pode emitir" e a pergunta de saude devolvida; o patcheado nao."""
import importlib.util
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import providers.llm.factory as llm_factory
from models.contact import Contact
from models.job import Job
from models.message import Message, MessageDirection, MessageMediaType
from models.user import User, UserRole
from utils.config import get_settings

PROD = Path(__file__).resolve().parents[2] / "docs" / "twin-role-inversion" / "prod"
ALERT_PHONE = "5511900000001"
BUGGY = "Ainda não, tô na mesma. Febre não baixou ontem à noite, tá ruim de engolir também.\n\nVc tá melhorando aí?"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def patched_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("prod_patched")
    done = subprocess.run([sys.executable, str(PROD / "aplicar_twin_roles.py"), "--origem", str(PROD / "originais"), "--saida", str(out)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return out


@pytest.fixture
def prod(monkeypatch, tmp_path):
    """Instala os modulos de producao (reais + stubs) e devolve um carregador do handler."""
    state = SimpleNamespace(reply=BUGGY, llm_calls=[], holding=False)

    async def fake_chat(messages, tools=None):
        state.llm_calls.append(messages)
        return SimpleNamespace(content=state.reply)

    monkeypatch.setattr(llm_factory, "chat_with_fallback", fake_chat, raising=False)
    for name in ("twin_audio_gate", "twin_autoreply_gate", "twin_commitment_guard", "twin_finance_guard"):
        monkeypatch.setitem(sys.modules, f"orchestrator.{name}", _module(f"orchestrator.{name}", PROD / "originais" / f"{name}.py"))
    policy = types.ModuleType("orchestrator.twin_policy")
    policy.holding_message_enabled = lambda: state.holding
    policy.risk_history_texts = lambda history, message_id: []
    policy.silent_skip_reason = lambda message, history, message_id: None
    monkeypatch.setitem(sys.modules, "orchestrator.twin_policy", policy)
    output_guard = types.ModuleType("orchestrator.twin_output_guard")
    output_guard.contains_internal_marker = lambda reply: False
    monkeypatch.setitem(sys.modules, "orchestrator.twin_output_guard", output_guard)
    risk = types.ModuleType("orchestrator.twin_risk_gate")                      # assinatura de PRODUCAO: (texto, historico) -> (bool, motivo)
    risk.is_high_risk_for_impersonation = lambda text, history_texts: (False, "")
    monkeypatch.setitem(sys.modules, "orchestrator.twin_risk_gate", risk)
    deps = types.ModuleType("jobs.owner_audio_dependencies")                    # modulo de producao nao recebido; so a excecao e importada
    deps.JobDependencyPending = type("JobDependencyPending", (RuntimeError,), {"__init__": lambda self, message, backoff=0: RuntimeError.__init__(self, message)})
    monkeypatch.setitem(sys.modules, "jobs.owner_audio_dependencies", deps)
    import jobs.registry as registry
    monkeypatch.setattr(registry, "job_handler", lambda name: (lambda fn: fn))   # nao re-registrar os handlers do repositorio

    def load(handlers_path: Path, twin_path: Path, tag: str):
        twin = _module(f"agents.darius_twin_{tag}", twin_path)
        twin._PROMPT_PATH = tmp_path / "darius_twin.md"
        twin._CONVERSATION_PATH = tmp_path / "twin_conversation.md"
        (tmp_path / "darius_twin.md").write_text("PERSONA", encoding="utf-8")
        (tmp_path / "twin_conversation.md").write_text("CONVERSA", encoding="utf-8")
        monkeypatch.setitem(sys.modules, "agents.darius_twin", twin)
        return _module(f"jobs.handlers_{tag}", handlers_path)

    state.load = load
    return state


@pytest.fixture
async def world(db_engine, monkeypatch):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    settings = get_settings()
    for name, value in dict(whatsapp_twin_mode_enabled=True, evolution_personal_instance="Dario-fora-de-uso", whatsapp_owner_alert_phone=ALERT_PHONE).items():
        monkeypatch.setattr(settings, name, value, raising=False)
    w = SimpleNamespace(sessions=sessions, instance="darioos")
    now = datetime.now(timezone.utc)
    async with sessions() as db:
        db.add(User(email="dono@example.com", full_name="Dono", hashed_password="x", role=UserRole.ADMIN))
        contact = Contact(name="Gerente LIBINA", phone="5511999990077", preferences={}, awaiting_reply_since=now)
        db.add(contact)
        await db.flush()
        w.contact_id = contact.id
        for minutes, direction, text, human, auto in [(120, MessageDirection.INBOUND, "Oi Netinho", False, False),
                                                      (119, MessageDirection.OUTBOUND, "Oi, tudo certo?", True, False)]:
            at = now - timedelta(minutes=minutes)
            db.add(Message(contact_id=contact.id, direction=direction, media_type=MessageMediaType.TEXT, content=text, whatsapp_instance=w.instance,
                           sent_by_human=human, is_autopilot_reply=auto, created_at=at, provider_timestamp=at))
        at = now - timedelta(minutes=1)
        pending = Message(contact_id=contact.id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content="Como vc está?",
                          whatsapp_instance=w.instance, created_at=at, provider_timestamp=at)
        db.add(pending)
        await db.commit()
        w.pending_id = pending.id
    return w


async def _run(handlers, world):
    async with world.sessions() as db:
        await handlers.twin_autopilot_check(db, {"contact_id": world.contact_id, "message_id": world.pending_id, "instance": world.instance})


async def _jobs(world):
    async with world.sessions() as db:
        rows = (await db.execute(select(Job).where(Job.name == "whatsapp.send_text").order_by(Job.id))).scalars().all()
        return [(j.payload["to"], j.payload["content"]) for j in rows]


async def _set_pending(world, text):
    async with world.sessions() as db:
        (await db.get(Message, world.pending_id)).content = text
        await db.commit()


def _to_contact(jobs):
    return [content for to, content in jobs if to != ALERT_PHONE]


# --------------------------------------------------------------------------------------------------- controle negativo: o ORIGINAL de producao
async def test_NEGATIVE_CONTROL_original_production_handler_sends_the_inverted_question(prod, world):
    handlers = prod.load(PROD / "originais" / "handlers.py", PROD / "originais" / "darius_twin.py", "orig1")
    await _run(handlers, world)
    assert _to_contact(await _jobs(world)) == [BUGGY]                                  # a pergunta de saude VOLTA ao contato


async def test_NEGATIVE_CONTROL_original_production_handler_sends_an_authorization(prod, world):
    prod.reply = "Pode emitir"
    handlers = prod.load(PROD / "originais" / "handlers.py", PROD / "originais" / "darius_twin.py", "orig2")
    await _run(handlers, world)
    assert _to_contact(await _jobs(world)) == ["Pode emitir"]


async def test_NEGATIVE_CONTROL_original_production_handler_answers_a_pure_farewell_to_a_bot(prod, world):
    await _set_pending(world, "👋")
    prod.reply = "👋"
    handlers = prod.load(PROD / "originais" / "handlers.py", PROD / "originais" / "darius_twin.py", "orig3")
    await _run(handlers, world)
    assert _to_contact(await _jobs(world)) == ["👋"]


# ------------------------------------------------------------------------------------------------------------------------ patcheado
async def test_patched_production_handler_fixes_the_libina_reply_and_labels_authorship(prod, world, patched_dir):
    handlers = prod.load(patched_dir / "handlers.py", patched_dir / "darius_twin.py", "pat1")
    await _run(handlers, world)
    assert _to_contact(await _jobs(world)) == ["Ainda não, tô na mesma. Febre não baixou ontem à noite, tá ruim de engolir também."]
    history = [(m.role, m.content) for m in prod.llm_calls[0] if m.role in ("user", "assistant")]
    assert history == [("user", "Oi Netinho"), ("assistant", "[Dário] Oi, tudo certo?"), ("user", "Como vc está?")]


async def test_patched_production_handler_holds_an_authorization_and_alerts_with_the_draft(prod, world, patched_dir):
    prod.reply = "Pode emitir"
    handlers = prod.load(patched_dir / "handlers.py", patched_dir / "darius_twin.py", "pat2")
    await _run(handlers, world)
    jobs = await _jobs(world)
    assert _to_contact(jobs) == []                                                     # nada ao contato (retencao silenciosa de producao)
    (alert,) = [content for to, content in jobs if to == ALERT_PHONE]
    assert "ato proibido ao Gêmeo: autorizacao" in alert and 'Rascunho que o gêmeo ia enviar: "Pode emitir"' in alert


@pytest.mark.parametrize("text", ["👋", "Até! 🙏", "Sou o assistente virtual da Igreja de Azusa. Como posso ajudar você hoje?",
                                  "✅ Teste do vigia de linhas: este é o caminho do alerta. Não responda."])
async def test_patched_production_handler_stays_silent_for_farewells_bots_and_own_alerts(prod, world, patched_dir, text):
    await _set_pending(world, text)
    handlers = prod.load(patched_dir / "handlers.py", patched_dir / "darius_twin.py", "pat3")
    await _run(handlers, world)
    assert await _jobs(world) == [] and prod.llm_calls == []


async def test_patched_production_handler_controls_normal_reply_still_goes_out(prod, world, patched_dir):
    await _set_pending(world, "Bom dia, tudo bem?")
    prod.reply = "Bom dia! Tudo certo por aqui. E contigo?"
    handlers = prod.load(patched_dir / "handlers.py", patched_dir / "darius_twin.py", "pat4")
    await _run(handlers, world)
    assert _to_contact(await _jobs(world)) == ["Bom dia! Tudo certo por aqui. E contigo?"]


async def test_patched_production_handler_kill_switches_by_environment(prod, world, patched_dir, monkeypatch):
    monkeypatch.setenv("TWIN_ACTION_GUARD", "0")
    prod.reply = "Pode emitir"
    handlers = prod.load(patched_dir / "handlers.py", patched_dir / "darius_twin.py", "pat5")
    await _run(handlers, world)
    assert _to_contact(await _jobs(world)) == ["Pode emitir"]
