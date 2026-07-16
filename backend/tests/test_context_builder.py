"""Context Builder: gathers short-term history, preferences/summary
(contact-scoped) and goals/tasks/calendar (owner-scoped) before the
Cognitive Pipeline plans a reply. Extracted from
CognitivePipeline._load_context (Fase 4.2); these tests cover the three
sources that had never been wired in before (goals/tasks/calendar) plus a
regression check that the moved contact-scoped logic still works.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from goals.service import GoalService
from models.calendar import CalendarEvent
from models.contact import Contact
from models.message import Message, MessageDirection, MessageMediaType
from models.goal import GoalPriority
from models.task import Task, TaskPriority, TaskStatus
from models.user import User
from orchestrator.context import ContextBuilder
from orchestrator.intent import Intent, IntentHypothesis, IntentResult
from orchestrator.priority import Priority, PriorityResult
from repositories.contact import ContactRepository


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def user(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="context@example.com", full_name="Dario", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def contact(session_factory) -> Contact:
    async with session_factory() as session:
        contact = Contact(name="Contato Contexto", phone="5511911112222")
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact


_INTENT = IntentResult(
    top=Intent.QUESTION,
    hypotheses=[IntentHypothesis(intent=Intent.QUESTION, confidence=0.9)],
)
_PRIORITY = PriorityResult(level=Priority.NORMAL, reason="")


def _sources(context) -> set[str]:
    return {m["source"] for m in context.memories}


# --- Goals ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ready_goals_are_gathered_into_context(session_factory, user):
    async with session_factory() as session:
        await GoalService(session).create_goal(
            user.id, "Aprender violão", priority=GoalPriority.HIGH
        )

    async with session_factory() as session:
        context = await ContextBuilder().build(
            session, user, None, "e aí, tudo bem?", _INTENT, _PRIORITY
        )

    assert "goal" in _sources(context)
    goal_entry = next(m for m in context.memories if m["source"] == "goal")
    assert "Aprender violão" in goal_entry["content"]


@pytest.mark.asyncio
async def test_awaiting_approval_goals_are_excluded_from_context(session_factory, user):
    async with session_factory() as session:
        await GoalService(session).create_goal(
            user.id, "Meta sigilosa", requires_approval=True
        )

    async with session_factory() as session:
        context = await ContextBuilder().build(
            session, user, None, "oi", _INTENT, _PRIORITY
        )

    assert "goal" not in _sources(context)


@pytest.mark.asyncio
async def test_goal_lookup_failure_does_not_block_context_building(
    session_factory, user
):
    with patch(
        "orchestrator.context.GoalService.ready_goals",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        async with session_factory() as session:
            context = await ContextBuilder().build(
                session, user, None, "oi", _INTENT, _PRIORITY
            )
    assert "goal" not in _sources(context)  # never raises, just skips this source


# --- Tasks -----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pending_tasks_are_gathered_into_context(session_factory, user):
    async with session_factory() as session:
        session.add(
            Task(user_id=user.id, title="Revisar contrato", priority=TaskPriority.HIGH)
        )
        await session.commit()

    async with session_factory() as session:
        context = await ContextBuilder().build(
            session, user, None, "oi", _INTENT, _PRIORITY
        )

    assert "task" in _sources(context)
    task_entry = next(m for m in context.memories if m["source"] == "task")
    assert "Revisar contrato" in task_entry["content"]


@pytest.mark.asyncio
async def test_completed_tasks_are_excluded_from_context(session_factory, user):
    async with session_factory() as session:
        session.add(Task(user_id=user.id, title="Já feita", status=TaskStatus.DONE))
        await session.commit()

    async with session_factory() as session:
        context = await ContextBuilder().build(
            session, user, None, "oi", _INTENT, _PRIORITY
        )

    assert "task" not in _sources(context)


# --- Calendar ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upcoming_calendar_events_are_gathered_into_context(
    session_factory, user
):
    async with session_factory() as session:
        session.add(
            CalendarEvent(
                user_id=user.id,
                title="Reunião com cliente",
                starts_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        await session.commit()

    async with session_factory() as session:
        context = await ContextBuilder().build(
            session, user, None, "oi", _INTENT, _PRIORITY
        )

    assert "calendar" in _sources(context)
    event_entry = next(m for m in context.memories if m["source"] == "calendar")
    assert "Reunião com cliente" in event_entry["content"]


@pytest.mark.asyncio
async def test_past_calendar_events_are_excluded_from_context(session_factory, user):
    async with session_factory() as session:
        session.add(
            CalendarEvent(
                user_id=user.id,
                title="Reunião de ontem",
                starts_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
        )
        await session.commit()

    async with session_factory() as session:
        context = await ContextBuilder().build(
            session, user, None, "oi", _INTENT, _PRIORITY
        )

    assert "calendar" not in _sources(context)


# --- Owner-scoped sources are independent of contact_id -----------------------------
@pytest.mark.asyncio
async def test_owner_scoped_sources_are_gathered_even_without_a_contact(
    session_factory, user
):
    async with session_factory() as session:
        await GoalService(session).create_goal(user.id, "Meta sem contato")

    async with session_factory() as session:
        context = await ContextBuilder().build(
            session, user, None, "oi", _INTENT, _PRIORITY
        )

    assert "goal" in _sources(context)
    assert context.history == []  # no contact_id -> no conversation history to load


# --- Contact-scoped sources (regression: moved from CognitivePipeline._load_context) --
@pytest.mark.asyncio
async def test_short_term_history_and_preferences_are_still_gathered(
    session_factory, user, contact
):
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
        await ContactRepository(session).update(
            await session.get(Contact, contact.id), preferences={"idioma": "pt-br"}
        )

    async with session_factory() as session:
        context = await ContextBuilder().build(
            session, user, contact.id, "e essa outra coisa?", _INTENT, _PRIORITY
        )

    assert len(context.history) == 1
    assert context.history[0].content == "mensagem anterior"
    assert "preferences" in _sources(context)


@pytest.mark.asyncio
async def test_memories_used_counts_every_source(session_factory, user, contact):
    async with session_factory() as session:
        await ContactRepository(session).update(
            await session.get(Contact, contact.id), preferences={"a": "b"}
        )
        await GoalService(session).create_goal(user.id, "Uma meta")
        session.add(Task(user_id=user.id, title="Uma tarefa"))
        await session.commit()

    async with session_factory() as session:
        context = await ContextBuilder().build(
            session, user, contact.id, "oi", _INTENT, _PRIORITY
        )

    assert context.memories_used == len(context.memories)
    assert context.memories_used >= 3  # preferences + goal + task at minimum
