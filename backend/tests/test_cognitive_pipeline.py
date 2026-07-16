"""Cognitive Pipeline (Fase 4.2) integration tests — the acceptance criteria
made concrete: a message arrives, intent/priority get classified, memory and
knowledge are consulted, a plan is made, the right agent(s) run with the
right tools, results are validated, memory is updated, and every step is
recorded in structured logs (the `logs` table via services.audit.record_log).
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from agents.executor import AgentResult, ExecutedStep
from models.contact import Contact
from models.log import LogEntry
from models.message import Message, MessageDirection, MessageMediaType
from models.user import User
from orchestrator.intent import Intent
from orchestrator.pipeline import CognitivePipeline, cognitive_pipeline
from orchestrator.planning import CognitivePlanner, PlanStepStatus
from orchestrator.priority import Priority
from providers.llm.base import LLMProvider, LLMResult, ToolCallRequest


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def user(session_factory) -> User:
    async with session_factory() as session:
        user = User(
            email="pipeline@example.com", full_name="Pipeline", hashed_password="x"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def contact(session_factory) -> Contact:
    async with session_factory() as session:
        contact = Contact(name="Contato Pipeline", phone="5511900998877")
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact


class ScriptedLLM(LLMProvider):
    name = "scripted"

    def __init__(self, result: LLMResult) -> None:
        self._result = result

    @property
    def enabled(self) -> bool:
        return True

    async def chat(self, messages, tools=None) -> LLMResult:
        return self._result

    async def embed(self, text: str) -> list[float]:
        return [0.0]


def _multi_step_plan_llm() -> ScriptedLLM:
    return ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="create_plan",
                    arguments={
                        "steps": [
                            {
                                "objective": "Marcar reunião amanhã às 14h",
                                "agent": "personal",
                                "depends_on": [],
                            },
                            {
                                "objective": "Enviar mensagem para o grupo da igreja",
                                "agent": "church",
                                "depends_on": [0],
                            },
                        ]
                    },
                )
            ]
        )
    )


# --- 1. Simple message ------------------------------------------------------
@pytest.mark.asyncio
async def test_simple_message_end_to_end(session_factory, user):
    async with session_factory() as session:
        result = await cognitive_pipeline.process(session, user, "Bom dia, tudo bem?")

    assert result.reply.strip()
    assert result.intent.top == Intent.GREETING
    assert len(result.plan.steps) == 1
    assert result.plan.steps[0].status == PlanStepStatus.DONE
    assert result.duration_ms >= 0
    assert "intent" in result.stage_durations_ms


# --- 2. Composite (multi-step) message --------------------------------------
@pytest.mark.asyncio
async def test_composite_message_executes_every_planned_step(session_factory, user):
    pipeline = CognitivePipeline(planner=CognitivePlanner(llm=_multi_step_plan_llm()))
    async with session_factory() as session:
        result = await pipeline.process(
            session,
            user,
            "Marque uma reunião amanhã às 14h e depois envie uma mensagem para o grupo da igreja.",
        )

    assert len(result.plan.steps) == 2
    assert result.plan.steps[0].agent == "personal"
    assert result.plan.steps[1].agent == "church"
    assert all(step.status == PlanStepStatus.DONE for step in result.plan.steps)
    assert all(step.result for step in result.plan.steps)


# --- 3. Multiple tools within one step --------------------------------------
@pytest.mark.asyncio
async def test_multiple_tools_executed_and_recorded_as_steps(
    session_factory, user, monkeypatch
):
    from agents import base as agents_base

    scripted = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1", name="create_task", arguments={"title": "Comprar pão"}
                ),
                ToolCallRequest(id="c2", name="list_tasks", arguments={}),
            ]
        )
    )
    call_count = {"n": 0}
    original_chat = scripted.chat

    async def chat(messages, tools=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return await original_chat(messages, tools)
        return LLMResult(content="Pronto, tarefa criada e lista consultada.")

    scripted.chat = chat
    monkeypatch.setattr(agents_base, "get_llm_provider", lambda: scripted)

    pipeline = CognitivePipeline(
        planner=CognitivePlanner(llm=ScriptedLLM(LLMResult(content="stub")))
    )
    async with session_factory() as session:
        result = await pipeline.process(
            session, user, "crie uma tarefa e liste minhas tarefas", contact_id=None
        )

    tool_names = {step.tool for step in result.steps}
    assert tool_names == {"create_task", "list_tasks"}
    assert all(step.status == "ok" for step in result.steps)


# --- 4/5. Validation retry on tool error, then giving up honestly ----------
@pytest.mark.asyncio
async def test_validation_retries_once_then_succeeds(
    session_factory, user, monkeypatch
):
    from orchestrator import pipeline as pipeline_module

    attempts = {"n": 0}
    failing_step = ExecutedStep(
        tool="create_task", arguments={}, result='{"error": "db down"}', status="error"
    )

    async def fake_run(**kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return AgentResult(reply="Feito.", steps=[failing_step])
        return AgentResult(reply="Feito na segunda tentativa.", steps=[])

    monkeypatch.setattr(pipeline_module.ai_orchestrator, "run", fake_run)

    async with session_factory() as session:
        result = await cognitive_pipeline.process(session, user, "crie uma tarefa")

    assert attempts["n"] == 2
    assert result.validation_attempts == 2
    assert result.plan.steps[0].status == PlanStepStatus.DONE
    assert result.reply == "Feito na segunda tentativa."


@pytest.mark.asyncio
async def test_validation_gives_up_after_max_attempts_but_never_goes_silent(
    session_factory, user, monkeypatch
):
    from orchestrator import pipeline as pipeline_module

    failing_step = ExecutedStep(
        tool="create_task", arguments={}, result='{"error": "db down"}', status="error"
    )

    async def always_fails(**kwargs):
        return AgentResult(reply="Não consegui completar.", steps=[failing_step])

    monkeypatch.setattr(pipeline_module.ai_orchestrator, "run", always_fails)

    async with session_factory() as session:
        result = await cognitive_pipeline.process(session, user, "crie uma tarefa")

    assert result.validation_attempts == pipeline_module._MAX_VALIDATION_ATTEMPTS
    assert result.plan.steps[0].status == PlanStepStatus.FAILED
    assert result.reply.strip()  # best-effort answer, never empty/silent


# --- 6. Automatic provider switch, exercised through the whole pipeline ----
@pytest.mark.asyncio
async def test_provider_failure_triggers_automatic_switch(
    session_factory, user, monkeypatch
):
    from utils.config import get_settings
    from agents import base as agents_base
    from providers.llm.factory import get_fallback_llm_provider

    class FailingLLM(LLMProvider):
        name = "failing"

        @property
        def enabled(self) -> bool:
            return True

        async def chat(self, messages, tools=None) -> LLMResult:
            raise RuntimeError("provider is down")

        async def embed(self, text: str) -> list[float]:
            return [0.0]

    working = ScriptedLLM(LLMResult(content="respondido pelo provider de reserva"))
    monkeypatch.setattr(agents_base, "get_llm_provider", lambda: FailingLLM())
    monkeypatch.setattr(get_settings(), "llm_fallback_provider", "anthropic")
    monkeypatch.setattr("providers.llm.factory._build", lambda name: working)
    get_fallback_llm_provider.cache_clear()

    try:
        async with session_factory() as session:
            result = await cognitive_pipeline.process(session, user, "oi")
    finally:
        get_fallback_llm_provider.cache_clear()

    assert result.reply == "respondido pelo provider de reserva"


# --- 7. Priority classification ---------------------------------------------
@pytest.mark.asyncio
async def test_urgent_message_is_classified_as_urgent_priority(session_factory, user):
    async with session_factory() as session:
        result = await cognitive_pipeline.process(
            session, user, "É urgente, socorro, preciso de ajuda agora"
        )
    assert result.priority.level == Priority.URGENT


# --- 8. Learning updates memory ---------------------------------------------
@pytest.mark.asyncio
async def test_learning_tags_contact_after_conversation(session_factory, user, contact):
    async with session_factory() as session:
        await cognitive_pipeline.process(
            session, user, "quero fazer um pedido na loja", contact_id=contact.id
        )

    async with session_factory() as session:
        refreshed = await session.get(Contact, contact.id)
    assert "loja" in refreshed.categories


# --- 9. Memory usage: short-term + preferences feed the agent --------------
@pytest.mark.asyncio
async def test_memory_context_is_loaded_and_passed_to_execution(
    session_factory, user, contact, monkeypatch
):
    from orchestrator import pipeline as pipeline_module

    async with session_factory() as session:
        session.add(
            Message(
                contact_id=contact.id,
                direction=MessageDirection.INBOUND,
                media_type=MessageMediaType.TEXT,
                content="mensagem anterior",
            )
        )
        await session.commit()

        from repositories.contact import ContactRepository

        await ContactRepository(session).update(
            await session.get(Contact, contact.id), preferences={"idioma": "pt-br"}
        )

    captured = {}

    async def fake_run(**kwargs):
        captured.update(kwargs)
        return AgentResult(reply="ok")

    monkeypatch.setattr(pipeline_module.ai_orchestrator, "run", fake_run)

    async with session_factory() as session:
        await cognitive_pipeline.process(
            session, user, "e essa outra coisa?", contact_id=contact.id
        )

    assert captured["history"]  # short-term conversation was loaded
    assert any(m.get("source") == "preferences" for m in captured["memories"])


# --- 10. Confirmation short-circuits execution ------------------------------
@pytest.mark.asyncio
async def test_needs_confirmation_stops_before_executing_any_step(
    session_factory, user
):
    confirm_llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="create_plan",
                    arguments={
                        "steps": [
                            {
                                "objective": "cancelar todos os pedidos da loja",
                                "agent": "store",
                            }
                        ],
                        "needs_confirmation": True,
                    },
                )
            ]
        )
    )
    pipeline = CognitivePipeline(planner=CognitivePlanner(llm=confirm_llm))
    async with session_factory() as session:
        result = await pipeline.process(session, user, "cancela tudo")

    assert result.awaiting_confirmation is True
    assert result.plan.steps[0].status == PlanStepStatus.PENDING
    assert "cancelar todos os pedidos da loja" in result.reply


# --- End-to-end via the real WhatsApp webhook + job worker ------------------
@pytest.mark.asyncio
async def test_whatsapp_flow_runs_through_the_cognitive_pipeline_and_logs_every_step(
    client, auth_headers, session_factory, monkeypatch
):
    from jobs.worker import JobWorker

    # Reuse the real worker against this test's session factory, same
    # pattern as tests/test_whatsapp_pipeline.py.
    monkeypatch.setattr("jobs.worker.async_session_factory", session_factory)
    monkeypatch.setattr("jobs.handlers.async_session_factory", session_factory)
    worker = JobWorker()

    response = await client.post(
        "/api/webhooks/whatsapp",
        json={
            "from": "5511977776655@c.us",
            "body": "Bom dia, quero saber sobre um produto da loja",
            "notifyName": "Cognitivo",
            "id": "wamid-cognitive-1",
            "type": "text",
        },
    )
    assert response.status_code == 200

    await worker.run_once()

    async with session_factory() as session:
        logs = (
            (
                await session.execute(
                    select(LogEntry).where(LogEntry.source == "cognitive_pipeline")
                )
            )
            .scalars()
            .all()
        )
    assert len(logs) == 1
    payload = logs[0].payload
    assert payload["intent"] in {i.value for i in Intent}
    assert payload["priority"] in {p.value for p in Priority}
    assert "stage_durations_ms" in payload
    assert payload["agents"]
