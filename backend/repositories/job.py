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
