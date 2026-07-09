"""Job service: enqueue and schedule background work."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from models.job import Job
from repositories.job import JobRepository
from utils.config import get_settings


class JobService:
    def __init__(self, session: AsyncSession) -> None:
        self.jobs = JobRepository(session)
        self.settings = get_settings()

    async def enqueue(
        self,
        name: str,
        payload: dict | None = None,
        delay_seconds: float = 0,
        max_attempts: int | None = None,
    ) -> Job:
        """Queue a job for the worker; delay_seconds > 0 schedules it for later."""
        return await self.jobs.create(
            name=name,
            payload=payload or {},
            max_attempts=max_attempts or self.settings.jobs_default_max_attempts,
            scheduled_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
        )
