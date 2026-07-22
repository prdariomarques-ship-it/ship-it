"""Shared data-fetching for the two context surfaces that both read
goals/tasks/calendar for the same owner: `orchestrator.context.ContextBuilder`
(per-message context for the Cognitive Pipeline) and
`observation.builder.ObservationContextBuilder` (the standing world-state
snapshot). Before this module existed, both re-implemented the identical
`GoalService.ready_goals` call, the identical `TaskRepository.list(...)`
call, and a byte-for-byte identical inline `CalendarEvent` query.

Deliberately fetch-only: no rendering (that's already shared, unchanged, via
`services.descriptions`), no error handling, no return-shape conversion.
Each caller keeps its own degradation policy (`ContextBuilder` logs and
returns an empty list per source; `ObservationContextBuilder` records the
failure in `CurrentContext.degraded_sources`) and its own output shape
(`Context.memories` is a flat `list[dict]`; `CurrentContext` uses typed
`ContextItem`s) — unifying either of those isn't required to remove the
actual duplication, so neither is touched here.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goals.service import GoalService
from models.calendar import CalendarEvent
from models.goal import Goal
from models.task import Task, TaskStatus
from repositories.task import TaskRepository


async def fetch_ready_goals(db: AsyncSession, user_id: int, limit: int) -> list[Goal]:
    return await GoalService(db).ready_goals(user_id, limit=limit)


async def fetch_pending_tasks(db: AsyncSession, user_id: int, limit: int) -> list[Task]:
    return await TaskRepository(db).list(
        user_id=user_id, status=TaskStatus.PENDING, limit=limit
    )


async def fetch_upcoming_calendar_events(
    db: AsyncSession, user_id: int, limit: int
) -> list[CalendarEvent]:
    statement = (
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.starts_at >= datetime.now(timezone.utc),
        )
        .order_by(CalendarEvent.starts_at.asc())
        .limit(limit)
    )
    return list((await db.execute(statement)).scalars().all())
