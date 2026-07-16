"""Job lifecycle events: published on the internal Event Bus and persisted to
the logs table (audit trail survives even if nobody is subscribed).

This used to talk to Redis directly; it now rides the shared EventBus so job
events and everything else (agent runs, inbound messages, ...) flow through
one consistent pub/sub instead of every module wiring its own Redis channel.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from events.bus import event_bus
from models.job import Job
from services.audit import record_log


class JobEventPublisher:
    async def publish(
        self, db: AsyncSession, job: Job, event: str, detail: str = ""
    ) -> None:
        payload = {
            "job_id": job.id,
            "job_name": job.name,
            "attempts": job.attempts,
            "status": job.status.value,
            "detail": detail,
            # The job's own enqueue payload (e.g. contact_id/phone) — lets
            # subscribers act on *what* failed, not just *that* it failed.
            "job_payload": dict(job.payload or {}),
        }

        level = "error" if event == "failed" else "info"
        await record_log(
            db,
            source=f"job:{job.name}",
            message=f"Job {job.id} {event}",
            level=level,
            payload=payload,
        )
        await event_bus.publish(f"job.{event}", payload)


job_event_publisher = JobEventPublisher()
