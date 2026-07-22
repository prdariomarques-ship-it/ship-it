"""Context Builder service for the Context Observation Engine.

Named `ObservationContextBuilder` (not `ContextBuilder`) to avoid colliding
with `orchestrator.context.ContextBuilder`, which this deliberately is not a
replacement for: that one builds a *per-message* context, scoped to one
conversation and gated by intent/priority (`needs_deep_context`), for the
Cognitive Pipeline to plan a reply. This one builds a *standing* snapshot of
the whole owner-scoped world state — goals, tasks, calendar, recent events,
conversations, pending work, memory — refreshed on a schedule and by events
(`observation/scheduler.py`, `observation/events.py`), independent of any
single inbound message. See docs/OBSERVATION_ENGINE.md for the full boundary.

Every source lookup is best-effort — same idiom as
`orchestrator.context.ContextBuilder`: a source that fails (dependency down,
table not migrated yet) is skipped and recorded in
`CurrentContext.degraded_sources`, never raised. Observation is an
enhancement, never a requirement blocking anything else.

Reuses, never reimplements:
- `orchestrator.context_sources.fetch_ready_goals/fetch_pending_tasks/
  fetch_upcoming_calendar_events` — the exact same goals/tasks/calendar
  queries `orchestrator.context.ContextBuilder` uses for the Cognitive
  Pipeline. Extracted into that shared module specifically because this
  file and `orchestrator/context.py` used to each run their own copy of
  all three queries (confirmed byte-for-byte identical for calendar) —
  this builder and that one now call the same functions; only the
  degradation policy (this file's `degraded_sources` list vs. that file's
  per-source try/except) and the return shape (`ContextItem` here,
  `dict` there) stay intentionally different.
- `repositories.job.JobRepository`, `repositories.message.MessageRepository`
  — existing repositories, unmodified (job.py gained one read-only method,
  `pending_by_name`, used by the scheduler, not by this builder).
- `services.descriptions.describe_goal/describe_task/describe_calendar_event`
  — the exact same rendering `orchestrator.context.ContextBuilder` uses, so a
  Goal/Task/CalendarEvent reads identically regardless of which context
  surface produced it.
- `repositories.base.SQLAlchemyRepository` — the same generic base every
  other repository extends, for the one source with no dedicated repository
  yet (`Embedding`) and for the one-off query (`LogEntry`) that
  `api/routes.py`/`admin/service.py` already write inline rather than
  through a repository — same precedent, not a new one.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.embedding import Embedding
from models.job import Job, JobStatus
from models.log import LogEntry
from models.message import Message, MessageDirection
from models.user import User
from observability.metrics import record_observation_source_error
from observation.models import ContextItem, CurrentContext
from orchestrator.context_sources import (
    fetch_pending_tasks,
    fetch_ready_goals,
    fetch_upcoming_calendar_events,
)
from repositories.base import SQLAlchemyRepository
from repositories.job import JobRepository
from repositories.message import MessageRepository
from services.descriptions import describe_calendar_event, describe_goal, describe_task
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class _EmbeddingRepo(SQLAlchemyRepository[Embedding]):
    model = Embedding


def _describe_log(entry: LogEntry) -> str:
    return f"[{entry.level}] {entry.source}: {entry.message}"


def _describe_message(message: Message) -> str:
    direction = "recebida" if message.direction == MessageDirection.INBOUND else "enviada"
    preview = message.content[:140]
    return f"contato {message.contact_id}, {direction}: {preview}"


def _describe_job(job: Job) -> str:
    return f"{job.name} ({job.status.value}, tentativa {job.attempts}/{job.max_attempts})"


def _describe_memory(embedding: Embedding) -> str:
    return f"[{embedding.source}] {embedding.content[:140]}"


class ObservationContextBuilder:
    async def build(
        self, db: AsyncSession, user: User, *, trigger: str = "scheduler"
    ) -> CurrentContext:
        limit = get_settings().observation_context_limit
        context = CurrentContext(user_id=user.id, trigger=trigger)

        sources = (
            ("goals", self._gather_goals),
            ("tasks", self._gather_tasks),
            ("calendar", self._gather_calendar),
            ("recent_events", self._gather_recent_events),
            ("conversations", self._gather_conversations),
            ("pending_work", self._gather_pending_work),
            ("memory", self._gather_memory),
        )
        for name, gather in sources:
            try:
                items = await gather(db, user, limit)
            except Exception as exc:  # noqa: BLE001 - observation is an enhancement, never a requirement
                logger.warning("Observation source %s skipped: %s", name, exc)
                record_observation_source_error(name)
                context.degraded_sources.append(name)
                continue
            setattr(context, name, items)

        return context

    async def _gather_goals(
        self, db: AsyncSession, user: User, limit: int
    ) -> list[ContextItem]:
        ready = await fetch_ready_goals(db, user.id, limit)
        return [ContextItem(source="goal", content=describe_goal(goal)) for goal in ready]

    async def _gather_tasks(
        self, db: AsyncSession, user: User, limit: int
    ) -> list[ContextItem]:
        tasks = await fetch_pending_tasks(db, user.id, limit)
        return [ContextItem(source="task", content=describe_task(task)) for task in tasks]

    async def _gather_calendar(
        self, db: AsyncSession, user: User, limit: int
    ) -> list[ContextItem]:
        events = await fetch_upcoming_calendar_events(db, user.id, limit)
        return [
            ContextItem(source="calendar", content=describe_calendar_event(event))
            for event in events
        ]

    async def _gather_recent_events(
        self, db: AsyncSession, user: User, limit: int
    ) -> list[ContextItem]:
        # LogEntry is the durable audit trail every domain already writes to
        # (goal/job lifecycle, pipeline runs, webhook activity) — inline
        # query, same precedent as api/routes.py and admin/service.py (no
        # dedicated LogRepository exists in this codebase; not one to add
        # here either).
        statement = select(LogEntry).order_by(LogEntry.id.desc()).limit(limit)
        entries = list((await db.execute(statement)).scalars().all())
        return [
            ContextItem(source="event", content=_describe_log(entry))
            for entry in entries
        ]

    async def _gather_conversations(
        self, db: AsyncSession, user: User, limit: int
    ) -> list[ContextItem]:
        messages = await MessageRepository(db).list(limit=limit)
        return [
            ContextItem(source="conversation", content=_describe_message(message))
            for message in messages
        ]

    async def _gather_pending_work(
        self, db: AsyncSession, user: User, limit: int
    ) -> list[ContextItem]:
        repo = JobRepository(db)
        queued = await repo.list(status=JobStatus.QUEUED, limit=limit)
        running = await repo.list(status=JobStatus.RUNNING, limit=limit)
        jobs = (queued + running)[:limit]
        return [ContextItem(source="job", content=_describe_job(job)) for job in jobs]

    async def _gather_memory(
        self, db: AsyncSession, user: User, limit: int
    ) -> list[ContextItem]:
        embeddings = await _EmbeddingRepo(db).list(limit=limit)
        return [
            ContextItem(source="memory", content=_describe_memory(embedding))
            for embedding in embeddings
        ]
