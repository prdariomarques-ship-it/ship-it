"""Repository for `financial_jobs` — independent of repositories/job.py on
purpose: this queue never reads, claims, or writes a row from `jobs`.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from investments.models import FinancialJob, FinancialJobStatus


class DuplicateChainError(RuntimeError):
    """Raised when a QUEUED/RUNNING row for this job name already exists —
    the unique partial index rejected the insert. Expected and handled,
    not a bug: this is the race-closing mechanism working as intended."""


class FinancialJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, job_id: int) -> FinancialJob | None:
        return await self.session.get(FinancialJob, job_id)

    async def create(
        self, *, name: str, payload: dict, max_attempts: int = 3, delay_seconds: float = 0
    ) -> FinancialJob:
        job = FinancialJob(
            name=name,
            payload=payload,
            max_attempts=max_attempts,
            scheduled_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
        )
        self.session.add(job)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DuplicateChainError(
                f"A queued/running {name!r} job already exists — not creating a second chain."
            ) from exc
        await self.session.refresh(job)
        return job

    async def due_jobs(self, now: datetime, limit: int = 10, for_update: bool = False) -> list[FinancialJob]:
        statement = (
            select(FinancialJob)
            .where(FinancialJob.status == FinancialJobStatus.QUEUED, FinancialJob.scheduled_at <= now)
            .order_by(FinancialJob.scheduled_at.asc())
            .limit(limit)
        )
        if for_update:
            statement = statement.with_for_update(skip_locked=True)
        return list((await self.session.execute(statement)).scalars().all())

    async def stale_running_jobs(self, started_before: datetime, limit: int = 50) -> list[FinancialJob]:
        statement = (
            select(FinancialJob)
            .where(FinancialJob.status == FinancialJobStatus.RUNNING, FinancialJob.started_at < started_before)
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def find_one(self, **filters) -> FinancialJob | None:
        statement = select(FinancialJob)
        for field, value in filters.items():
            statement = statement.where(getattr(FinancialJob, field) == value)
        return (await self.session.execute(statement)).scalars().first()

    async def list(self, *, limit: int = 50, offset: int = 0, **filters) -> list[FinancialJob]:
        statement = select(FinancialJob)
        for field, value in filters.items():
            statement = statement.where(getattr(FinancialJob, field) == value)
        statement = statement.order_by(FinancialJob.id.desc()).limit(limit).offset(offset)
        return list((await self.session.execute(statement)).scalars().all())

    async def update(self, job: FinancialJob, **fields) -> FinancialJob:
        for key, value in fields.items():
            setattr(job, key, value)
        await self.session.commit()
        await self.session.refresh(job)
        return job
