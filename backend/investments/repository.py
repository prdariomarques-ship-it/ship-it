"""Repository for `financial_jobs` — independent of repositories/job.py on
purpose: this queue never reads, claims, or writes a row from `jobs`.

Ownership/lease: every RUNNING row carries a `lease_token` (stamped at
claim time) and a `lease_expires_at`. Recovery of a stale RUNNING row and
every final status write are conditioned on that token via an atomic
`UPDATE ... WHERE lease_token = :token` (rowcount checked, never assumed)
— so two processes racing to recover the same job can't both "win", and a
slow-but-still-alive execution that a recovery reclaimed can't later
clobber the new owner's result with its own stale write.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from investments.models import FinancialJob, FinancialJobStatus
from utils.logging import get_logger

logger = get_logger(__name__)

# How long a claimed job may legitimately run before its lease is
# considered expired and eligible for recovery. Generous relative to this
# package's actual handlers (one HTTP fetch + one HTTP post, normally
# single-digit seconds) — a run past this is treated as crashed/hung, not
# as "still working".
LEASE_DURATION_SECONDS = 300


class DuplicateChainError(RuntimeError):
    """Raised when a QUEUED/RUNNING row for this job name already exists —
    the unique partial index rejected the insert. Expected and handled,
    not a bug: this is the race-closing mechanism working as intended."""


class DuplicateReportError(RuntimeError):
    """Raised when idempotency_key collides with an existing row — this
    report/message was already produced (by an earlier attempt of the
    same generator job), so this attempt must not produce a second one."""


class FinancialJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, job_id: int) -> FinancialJob | None:
        return await self.session.get(FinancialJob, job_id)

    async def create(
        self, *, name: str, payload: dict, max_attempts: int = 3, delay_seconds: float = 0,
        idempotency_key: str | None = None,
    ) -> FinancialJob:
        job = FinancialJob(
            name=name,
            payload=payload,
            max_attempts=max_attempts,
            scheduled_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
            idempotency_key=idempotency_key,
        )
        self.session.add(job)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if idempotency_key is not None:
                raise DuplicateReportError(
                    f"A row with idempotency_key={idempotency_key!r} already exists — "
                    "this report/message was already produced, not creating a second one."
                ) from exc
            raise DuplicateChainError(
                f"A queued/running {name!r} job already exists — not creating a second chain."
            ) from exc
        await self.session.refresh(job)
        return job

    async def claim_due(self, now: datetime, limit: int = 10) -> list[FinancialJob]:
        """SKIP LOCKED select + same-transaction lease stamp — safe under
        real Postgres concurrency (two workers can never select the same
        row; SQLAlchemy's SQLite dialect silently drops SKIP LOCKED
        entirely, but SQLite's own single-writer model makes a second
        concurrent claimer structurally impossible there anyway — this
        specific guarantee is NOT validated against real Postgres locking
        in this sandbox, see tests/test_financial_worker_postgres.py)."""
        statement = (
            select(FinancialJob)
            .where(FinancialJob.status == FinancialJobStatus.QUEUED, FinancialJob.scheduled_at <= now)
            .order_by(FinancialJob.scheduled_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        jobs = list((await self.session.execute(statement)).scalars().all())
        for job in jobs:
            job.status = FinancialJobStatus.RUNNING
            job.started_at = now
            job.attempts += 1
            job.lease_token = uuid.uuid4().hex
            job.lease_expires_at = now + timedelta(seconds=LEASE_DURATION_SECONDS)
        await self.session.commit()
        return jobs

    async def stale_running_candidates(self, now: datetime, limit: int = 50) -> list[FinancialJob]:
        """Candidates only — NOT yet claimed for recovery. Each must still
        go through try_recover_stale's atomic, lease-checked UPDATE before
        being treated as actually recovered; a plain read here is cheap
        and fine for ordering, since it can't grant ownership by itself."""
        statement = (
            select(FinancialJob)
            .where(FinancialJob.status == FinancialJobStatus.RUNNING, FinancialJob.lease_expires_at < now)
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def try_recover_stale(
        self, job_id: int, lease_token: str | None, now: datetime, *,
        failed: bool, last_error: str, result: dict | None = None,
    ) -> bool:
        """Atomic compare-and-swap: only takes effect if the row is STILL
        RUNNING with THIS EXACT lease_token at the moment of the UPDATE.
        Returns False (no write happened) if another process already
        recovered it, or it finished normally in the meantime — the
        caller must treat that as "someone else already handled it"."""
        # lease_token is cleared in BOTH branches — this is the exact bug a
        # test of this method caught: leaving the old token in place after
        # recovering to QUEUED meant the original (stale) execution could
        # still complete_if_owner() successfully later, using that same
        # now-"recovered" token, clobbering whatever the new claim does.
        new_values = (
            {
                "status": FinancialJobStatus.FAILED, "finished_at": now,
                "last_error": last_error, "result": result, "lease_token": None,
            }
            if failed
            else {
                "status": FinancialJobStatus.QUEUED, "scheduled_at": now,
                "last_error": last_error, "lease_token": None, "lease_expires_at": None,
            }
        )
        statement = (
            sa_update(FinancialJob)
            .where(
                FinancialJob.id == job_id,
                FinancialJob.status == FinancialJobStatus.RUNNING,
                FinancialJob.lease_token == lease_token,
            )
            .values(**new_values)
        )
        result_proxy = await self.session.execute(statement)
        await self.session.commit()
        return result_proxy.rowcount == 1

    async def complete_if_owner(
        self, job_id: int, lease_token: str | None, *, status: FinancialJobStatus, finished_at: datetime,
        result: dict | None, last_error: str | None = None,
    ) -> bool:
        """Terminal status write (no reschedule), conditioned on still
        holding the lease. Returns False if the lease no longer matches —
        a recovery already reclaimed this row, so this execution's result
        is stale and must be discarded, not written."""
        statement = (
            sa_update(FinancialJob)
            .where(FinancialJob.id == job_id, FinancialJob.lease_token == lease_token)
            .values(status=status, finished_at=finished_at, result=result, last_error=last_error)
        )
        result_proxy = await self.session.execute(statement)
        await self.session.commit()
        return result_proxy.rowcount == 1

    async def complete_and_reschedule(
        self, job_id: int, lease_token: str | None, *, result: dict | None, finished_at: datetime,
        reschedule_name: str, reschedule_delay_seconds: float,
    ) -> tuple[bool, bool]:
        """Marks the job SUCCEEDED and creates its self-rescheduled
        successor in ONE transaction — so no other process can ever
        observe "current terminal, successor missing" as a committed
        fact. That gap, when it existed as two separate commits, is
        exactly what let a concurrent healing pass insert an off-cadence
        immediate successor in the window between them.

        Returns (completed, rescheduled). completed=False means the lease
        didn't match (stale execution — nothing was written, including no
        successor). rescheduled=False while completed=True means a chain
        for this name was already active (a SAVEPOINT absorbs that
        IntegrityError so it doesn't roll back the completion)."""
        update_statement = (
            sa_update(FinancialJob)
            .where(FinancialJob.id == job_id, FinancialJob.lease_token == lease_token)
            .values(status=FinancialJobStatus.SUCCEEDED, finished_at=finished_at, result=result)
        )
        update_result = await self.session.execute(update_statement)
        completed = update_result.rowcount == 1

        rescheduled = False
        if completed:
            try:
                async with self.session.begin_nested():
                    successor = FinancialJob(
                        name=reschedule_name, payload={},
                        scheduled_at=datetime.now(timezone.utc) + timedelta(seconds=reschedule_delay_seconds),
                    )
                    self.session.add(successor)
                    await self.session.flush()
                rescheduled = True
            except IntegrityError:
                logger.debug("Reschedule for %s skipped: a chain is already queued/running", reschedule_name)

        await self.session.commit()
        return completed, rescheduled

    async def retry_or_fail_if_owner(
        self, job_id: int, lease_token: str | None, *, attempts: int, max_attempts: int,
        backoff_seconds: float, error: str,
    ) -> bool:
        """Failure-path terminal/retry write, conditioned on still holding
        the lease — same reasoning as complete_if_owner: a stale execution
        (lease already reclaimed by a recovery) must not be able to shove
        this job back into QUEUED or FAILED out from under the new owner."""
        now = datetime.now(timezone.utc)
        new_values = (
            {"status": FinancialJobStatus.FAILED, "finished_at": now, "last_error": error}
            if attempts >= max_attempts
            else {"status": FinancialJobStatus.QUEUED, "scheduled_at": now + timedelta(seconds=backoff_seconds), "last_error": error}
        )
        statement = (
            sa_update(FinancialJob)
            .where(FinancialJob.id == job_id, FinancialJob.lease_token == lease_token)
            .values(**new_values)
        )
        result_proxy = await self.session.execute(statement)
        await self.session.commit()
        return result_proxy.rowcount == 1

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
        """Unconditional update — test/admin convenience only. Worker
        logic must use the lease-conditioned methods above, never this."""
        for key, value in fields.items():
            setattr(job, key, value)
        await self.session.commit()
        await self.session.refresh(job)
        return job
