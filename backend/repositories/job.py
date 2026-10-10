from datetime import datetime

from sqlalchemy import select

from models.job import Job, JobStatus
from repositories.base import SQLAlchemyRepository


class JobRepository(SQLAlchemyRepository[Job]):
    model = Job

    async def due_jobs(
        self, now: datetime, limit: int = 10, for_update: bool = False
    ) -> list[Job]:
        statement = (
            select(Job)
            .where(Job.status == JobStatus.QUEUED, Job.scheduled_at <= now)
            .order_by(Job.scheduled_at.asc())
            .limit(limit)
        )
        if for_update:
            # On Postgres, competing workers skip rows another worker already
            # claimed; SQLite ignores the clause (single-writer anyway).
            statement = statement.with_for_update(skip_locked=True)
        return list((await self.session.execute(statement)).scalars().all())

    async def stale_running_jobs(
        self, started_before: datetime, limit: int = 50
    ) -> list[Job]:
        """Jobs stuck in RUNNING — the worker that claimed them died mid-flight."""
        statement = (
            select(Job)
            .where(Job.status == JobStatus.RUNNING, Job.started_at < started_before)
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def pending_by_name(self, name: str) -> Job | None:
        """First QUEUED or RUNNING job with this name — lets a self-rescheduling
        handler (e.g. observation.tick) check whether its own chain is already
        alive before enqueueing a competing one (restart) or pull it forward
        (an event that warrants an earlier run than the next scheduled tick)."""
        statement = (
            select(Job)
            .where(Job.name == name, Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
            .limit(1)
        )
        return (await self.session.execute(statement)).scalars().first()

    async def has_inbound_reply(self, message_id: int) -> bool:
        """Whether a reply-dispatch job for this inbound `message_id`
        already exists -- any status, not just QUEUED/RUNNING, since the
        question is "was the enqueue step already committed", not "is it
        still pending". `webhooks/router.py`'s `dispatch_inbound` is the
        only place that ever enqueues one of these, and depending on
        settings it can be more than one of them for the same message
        (store_whatsapp_enabled's `workflow.trigger` branch is independent
        of auto_reply_enabled's twin/process_inbound branch) -- checked
        together, not just the first one found.

        Review finding (round 6): jobs/handlers.py's
        `transcribe_whatsapp_audio` calls this to resume safely after a
        crash between persisting the transcript and enqueueing the reply,
        without enqueueing a second, duplicate reply -- but it never
        existed, a guaranteed AttributeError on every audio message.

        `workflow.trigger`'s `message_id` is nested under `data` (see
        dispatch_inbound: `{"workflow": ..., "data": {"message_id": ...}}`),
        unlike `whatsapp.process_inbound`/`whatsapp.twin_autopilot_check`,
        which carry it at the payload's top level -- checked as two
        separate queries for exactly that reason, not one that happens to
        get it wrong for one of the three job names."""
        flat = await self.session.execute(
            select(Job.id)
            .where(
                Job.name.in_(("whatsapp.process_inbound", "whatsapp.twin_autopilot_check")),
                Job.payload["message_id"].as_integer() == message_id,
            )
            .limit(1)
        )
        if flat.first() is not None:
            return True
        nested = await self.session.execute(
            select(Job.id)
            .where(
                Job.name == "workflow.trigger",
                Job.payload["data"]["message_id"].as_integer() == message_id,
            )
            .limit(1)
        )
        return nested.first() is not None
