from datetime import datetime

from sqlalchemy import select

from models.job import Job, JobStatus
from repositories.base import SQLAlchemyRepository


class JobRepository(SQLAlchemyRepository[Job]):
    model = Job

    async def due_jobs(self, now: datetime, limit: int = 10) -> list[Job]:
        statement = (
            select(Job)
            .where(Job.status == JobStatus.QUEUED, Job.scheduled_at <= now)
            .order_by(Job.scheduled_at.asc())
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())
