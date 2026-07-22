"""Context Builder service (observation/builder.py): gathers goals, tasks,
calendar, recent events, conversations, pending work and memory into one
CurrentContext snapshot. Same testing shape as tests/test_context_builder.py
(which covers orchestrator.context.ContextBuilder, the per-message sibling
this one deliberately does not replace) — one section per dimension, plus a
best-effort/degradation section.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from goals.service import GoalService
from models.calendar import CalendarEvent
from models.contact import Contact
from models.embedding import Embedding
from models.goal import GoalPriority
from models.job import Job, JobStatus
from models.log import LogEntry
from models.message import Message, MessageDirection, MessageMediaType
from models.task import Task, TaskPriority, TaskStatus
from models.user import User
from observation.builder import ObservationContextBuilder


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def user(session_factory) -> User:
    async with session_factory() as session:
        user = User(
            email="observer@example.com", full_name="Dario", hashed_password="x"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def contact(session_factory) -> Contact:
    async with session_factory() as session:
        contact = Contact(name="Contato Observado", phone="5511900000000")
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact


def _by_source(context, source: str) -> list[str]:
    return [item.content for item in getattr(context, source)]


# --- Goals -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ready_goals_are_gathered(session_factory, user):
    async with session_factory() as session:
        await GoalService(session).create_goal(
            user.id, "Aprender violão", priority=GoalPriority.HIGH
        )

    async with session_factory() as session:
        context = await ObservationContextBuilder().build(session, user)

    assert "Aprender violão" in " ".join(_by_source(context, "goals"))
    assert "goals" not in context.degraded_sources


@pytest.mark.asyncio
async def test_awaiting_approval_goals_are_excluded(session_factory, user):
    async with session_factory() as session:
        await GoalService(session).create_goal(
            user.id, "Meta sigilosa", requires_approval=True
        )

    async with session_factory() as session:
        context = await ObservationContextBuilder().build(session, user)

    assert context.goals == []


# --- Tasks ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pending_tasks_are_gathered(session_factory, user):
    async with session_factory() as session:
        session.add(
            Task(user_id=user.id, title="Revisar contrato", priority=TaskPriority.HIGH)
        )
        await session.commit()

    async with session_factory() as session:
        context = await ObservationContextBuilder().build(session, user)

    assert "Revisar contrato" in " ".join(_by_source(context, "tasks"))


@pytest.mark.asyncio
async def test_completed_tasks_are_excluded(session_factory, user):
    async with session_factory() as session:
        session.add(Task(user_id=user.id, title="Já feita", status=TaskStatus.DONE))
        await session.commit()

    async with session_factory() as session:
        context = await ObservationContextBuilder().build(session, user)

    assert context.tasks == []


# --- Calendar --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upcoming_calendar_events_are_gathered(session_factory, user):
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
        context = await ObservationContextBuilder().build(session, user)

    assert "Reunião com cliente" in " ".join(_by_source(context, "calendar"))


@pytest.mark.asyncio
async def test_past_calendar_events_are_excluded(session_factory, user):
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
        context = await ObservationContextBuilder().build(session, user)

    assert context.calendar == []


# --- Recent events (logs) ---------------------------------------------------------
@pytest.mark.asyncio
async def test_recent_events_are_gathered_from_logs(session_factory, user):
    async with session_factory() as session:
        session.add(LogEntry(source="webhook", message="Mensagem recebida"))
        await session.commit()

    async with session_factory() as session:
        context = await ObservationContextBuilder().build(session, user)

    assert "Mensagem recebida" in " ".join(_by_source(context, "recent_events"))


# --- Conversations (recent messages) ----------------------------------------------
@pytest.mark.asyncio
async def test_conversations_are_gathered_from_recent_messages(
    session_factory, user, contact
):
    async with session_factory() as session:
        session.add(
            Message(
                contact_id=contact.id,
                direction=MessageDirection.INBOUND,
                media_type=MessageMediaType.TEXT,
                content="oi, tudo bem?",
            )
        )
        await session.commit()

    async with session_factory() as session:
        context = await ObservationContextBuilder().build(session, user)

    assert "oi, tudo bem?" in " ".join(_by_source(context, "conversations"))


# --- Pending work (jobs) -----------------------------------------------------------
@pytest.mark.asyncio
async def test_pending_work_gathers_queued_and_running_jobs(session_factory, user):
    async with session_factory() as session:
        session.add(Job(name="contact.summarize", status=JobStatus.QUEUED))
        session.add(Job(name="memory.embed", status=JobStatus.RUNNING))
        session.add(Job(name="whatsapp.send_text", status=JobStatus.SUCCEEDED))
        await session.commit()

    async with session_factory() as session:
        context = await ObservationContextBuilder().build(session, user)

    names = " ".join(_by_source(context, "pending_work"))
    assert "contact.summarize" in names
    assert "memory.embed" in names
    assert "whatsapp.send_text" not in names  # SUCCEEDED is not pending


# --- Memory -----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_memory_is_gathered_from_recent_embeddings(session_factory, user):
    async with session_factory() as session:
        session.add(
            Embedding(source="goal", content="Meta concluída: Aprender violão", vector_id="v1")
        )
        await session.commit()

    async with session_factory() as session:
        context = await ObservationContextBuilder().build(session, user)

    assert "Meta concluída" in " ".join(_by_source(context, "memory"))


# --- Best-effort / degradation -----------------------------------------------------
@pytest.mark.asyncio
async def test_a_failing_source_is_skipped_and_recorded_without_blocking_the_rest(
    session_factory, user
):
    async with session_factory() as session:
        session.add(
            Task(user_id=user.id, title="Sobrevive ao erro de outra fonte")
        )
        await session.commit()

    with patch(
        "observation.builder.fetch_ready_goals",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        async with session_factory() as session:
            context = await ObservationContextBuilder().build(session, user)

    assert context.goals == []
    assert context.degraded_sources == ["goals"]
    assert "Sobrevive ao erro de outra fonte" in " ".join(_by_source(context, "tasks"))


@pytest.mark.asyncio
async def test_no_failures_means_no_degraded_sources(session_factory, user):
    async with session_factory() as session:
        context = await ObservationContextBuilder().build(session, user)

    assert context.degraded_sources == []


# --- Trigger / metadata -------------------------------------------------------------
@pytest.mark.asyncio
async def test_trigger_is_recorded_on_the_snapshot(session_factory, user):
    async with session_factory() as session:
        context = await ObservationContextBuilder().build(
            session, user, trigger="event:goal.created"
        )

    assert context.trigger == "event:goal.created"
    assert context.user_id == user.id


@pytest.mark.asyncio
async def test_item_count_and_is_empty(session_factory, user):
    async with session_factory() as session:
        empty_context = await ObservationContextBuilder().build(session, user)
    assert empty_context.is_empty
    assert empty_context.item_count == 0

    async with session_factory() as session:
        await GoalService(session).create_goal(user.id, "Uma meta")

    async with session_factory() as session:
        context = await ObservationContextBuilder().build(session, user)
    assert not context.is_empty
    # create_goal also writes a "goal.created" LogEntry (see goals/events.py),
    # so recent_events picks it up too — only goals is asserted precisely.
    assert len(context.goals) == 1
    assert context.item_count >= 1
