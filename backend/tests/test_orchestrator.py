"""AI Orchestrator: single entry point for agent selection, execution and events."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from agents.registry import UnknownAgentError
from events.bus import event_bus
from models.user import User
from orchestrator.service import AgentTimeoutError, ai_orchestrator


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def user(db_session) -> User:
    user = User(email="orch@example.com", full_name="Orch", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_orchestrator_runs_the_selected_agent(db_session, user):
    result = await ai_orchestrator.run(
        db=db_session, user=user, message="oi", agent_name="personal"
    )
    assert result.reply  # stub reply without an LLM key configured, but a real run


@pytest.mark.asyncio
async def test_orchestrator_raises_for_unknown_agent(db_session, user):
    with pytest.raises(UnknownAgentError):
        await ai_orchestrator.run(
            db=db_session, user=user, message="oi", agent_name="nope"
        )


@pytest.mark.asyncio
async def test_orchestrator_publishes_selection_and_reply_events(db_session, user):
    events = []

    async def handler(event):
        events.append(event)

    event_bus.subscribe("agent.selected", handler)
    event_bus.subscribe("agent.replied", handler)
    try:
        await ai_orchestrator.run(
            db=db_session, user=user, message="oi", agent_name="content", contact_id=42
        )
    finally:
        event_bus.unsubscribe_all()

    names = [event.name for event in events]
    assert names == ["agent.selected", "agent.replied"]
    assert events[0].payload == {
        "agent": "content",
        "contact_id": 42,
        "user_id": user.id,
    }
    assert events[1].payload["agent"] == "content"
    assert "tool_calls" in events[1].payload
    assert "memories_used" in events[1].payload


@pytest.mark.asyncio
async def test_unknown_agent_does_not_publish_any_event(db_session, user):
    events = []

    async def handler(event):
        events.append(event)

    event_bus.subscribe("agent.selected", handler)
    try:
        with pytest.raises(UnknownAgentError):
            await ai_orchestrator.run(
                db=db_session, user=user, message="oi", agent_name="nope"
            )
    finally:
        event_bus.unsubscribe_all()

    assert events == []


@pytest.mark.asyncio
async def test_orchestrator_times_out_a_hung_agent(db_session, user, monkeypatch):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "agent_run_timeout_seconds", 0.05)

    async def _hangs_forever(
        self, db, user, message, contact_id=None, memories=None, history=None
    ):
        await asyncio.sleep(10)

    monkeypatch.setattr("agents.base.BaseAgent.run", _hangs_forever)

    events = []

    async def handler(event):
        events.append(event)

    event_bus.subscribe("agent.failed", handler)
    try:
        with pytest.raises(AgentTimeoutError):
            await ai_orchestrator.run(
                db=db_session, user=user, message="oi", agent_name="personal"
            )
    finally:
        event_bus.unsubscribe_all()

    assert len(events) == 1
    assert events[0].payload == {
        "agent": "personal",
        "contact_id": None,
        "user_id": user.id,
        "reason": "timeout",
    }


@pytest.mark.asyncio
async def test_orchestrator_records_agent_run_metrics(db_session, user):
    from observability.metrics import AGENT_RUN_DURATION, AGENT_RUNS

    before = AGENT_RUNS.labels("personal", "openai", "ok")._value.get()
    await ai_orchestrator.run(
        db=db_session, user=user, message="oi", agent_name="personal"
    )
    after = AGENT_RUNS.labels("personal", "openai", "ok")._value.get()

    assert after == before + 1
    assert AGENT_RUN_DURATION.labels("personal")._sum.get() >= 0
