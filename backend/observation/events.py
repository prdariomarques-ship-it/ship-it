"""Event integration for the Context Observation Engine.

Goal, job and agent/Cognitive-Pipeline activity (`goal.*`, `job.*`,
`agent.*` — already published by `goals/events.py`, `jobs/events.py` and
`orchestrator/service.py`, nothing new emitted here) means the world state
just changed, so the next scheduled tick (up to `OBSERVATION_INTERVAL_SECONDS`
away) may be stale for longer than a caller can tolerate. Rather than
rebuild synchronously inside the event handler (the publisher's session may
not be safe to reuse, and a slow rebuild would block whoever published the
event), this pulls the already-queued `observation.tick` job forward to run
now — same debounce idiom `jobs/handlers.py::_apologize_after_failed_auto_reply`
uses (open a fresh session, react, done), and it naturally coalesces bursts
of events into a single near-immediate tick instead of one rebuild per event.

If no tick is queued (observation disabled, or the scheduler was never
seeded), this is a no-op — event integration reacts to the scheduler's
chain, it does not start one; that stays `observation.scheduler.start`'s job
alone, called once from app startup.
"""

from datetime import datetime, timezone

from database.session import async_session_factory
from events.bus import Event, event_bus
from observation.scheduler import JOB_NAME
from repositories.job import JobRepository
from utils.logging import get_logger

logger = get_logger(__name__)

# Domains whose activity should refresh CurrentContext sooner than the next
# scheduled tick. Cognitive Pipeline runs publish under "agent.*"
# (orchestrator/service.py) — this is the Context Observation Engine's reuse
# of the Cognitive Pipeline: it reacts to what the pipeline already emits,
# rather than the pipeline depending on it.
_TRIGGER_DOMAINS = ("goal.*", "job.*", "agent.*")


def register_event_subscribers() -> None:
    """Wired explicitly from app startup (main.py), same as
    `jobs.handlers.register_event_subscribers` — never a bare module-level
    side effect, so tests can re-arm this after the per-test Event Bus
    reset."""
    for domain in _TRIGGER_DOMAINS:
        event_bus.subscribe(domain, _pull_tick_forward)


async def _pull_tick_forward(event: Event) -> None:
    if event.name.startswith("job.") and event.payload.get("job_name") == JOB_NAME:
        return  # the tick's own lifecycle events must not re-trigger itself

    async with async_session_factory() as session:
        repository = JobRepository(session)
        job = await repository.pending_by_name(JOB_NAME)
        if job is None:
            return
        await repository.update(job, scheduled_at=datetime.now(timezone.utc))
        logger.debug(
            "Observation tick pulled forward by %s (job %s)", event.name, job.id
        )
