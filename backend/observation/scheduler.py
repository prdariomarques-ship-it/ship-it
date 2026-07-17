"""Observation Scheduler: keeps `CurrentContext` fresh without a new timer
primitive — reuses the durable job queue (`jobs/`) exactly like every other
restart-safe recurring concern in this codebase already does.

`observation.tick` is a self-rescheduling job handler: each run rebuilds the
snapshot for the instance owner, then enqueues its own next run
`OBSERVATION_INTERVAL_SECONDS` later. There is no separate Scheduler
component — `jobs/worker.py::JobWorker` (async polling, atomic claim,
crash recovery, all already built and tested) *is* the scheduler; this
module only supplies its handler and the one-time seed that starts the
chain. This is what makes the engine restart-safe: the next tick's `Job` row
is committed to Postgres before this run returns, so a crash before the next
tick fires just means `JobWorker._recover_stale`/the normal due-job poll
picks the chain back up on the next process start — no separate persistence
for the snapshot itself is needed (see `observation/engine.py`).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from jobs.registry import job_handler
from jobs.service import JobService
from observation.engine import context_observation_engine
from repositories.job import JobRepository
from repositories.user import UserRepository
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

JOB_NAME = "observation.tick"


@job_handler(JOB_NAME)
async def observation_tick(db: AsyncSession, payload: dict) -> None:
    """Rebuild `CurrentContext` for the instance owner, then reschedule self.

    Best-effort at the source level: `ContextObservationEngine.observe`
    already swallows individual source failures (`observation/builder.py`).
    This handler only guards against there being no owner yet (fresh
    install, no admin registered) — and reschedules regardless, so the
    chain never dies waiting for one.
    """
    settings = get_settings()
    owner = await UserRepository(db).get_first_admin()
    if owner is not None:
        await context_observation_engine.observe(db, owner, trigger="scheduler")
    else:
        logger.debug("Observation tick skipped: no admin user registered yet")

    await JobService(db).enqueue(
        JOB_NAME, delay_seconds=settings.observation_interval_seconds
    )


async def start(db: AsyncSession) -> None:
    """Seed the first tick. Idempotent: skips if a tick is already
    QUEUED/RUNNING, so an app restart never spawns a second, competing
    chain — the existing one (persisted across the restart, same as any
    other job) just keeps going."""
    settings = get_settings()
    if not settings.observation_enabled:
        return
    if await JobRepository(db).pending_by_name(JOB_NAME) is not None:
        return
    await JobService(db).enqueue(JOB_NAME, delay_seconds=0)
