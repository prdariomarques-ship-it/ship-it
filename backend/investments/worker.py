"""Standalone worker for `financial_jobs` — its own polling loop, its own
retry/backoff, its own small handler registry. Deliberately does not import
jobs.worker, jobs.registry, jobs.events, or models.job: nothing here can
claim, execute, or even see a WhatsApp job.

Run as its own process (python -m investments), never inside the FastAPI
app's lifespan — a crash or a slow Yahoo Finance/Telegram response here
cannot block or compete with the WhatsApp request-handling event loop,
because it isn't the same process.
"""
import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from database.session import async_session_factory
from investments.models import FinancialJob, FinancialJobStatus
from investments.repository import DuplicateChainError, FinancialJobRepository
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Reschedule:
    """A handler returns this instead of a plain result dict to re-arm its
    own chain. The worker applies it only after the current row is already
    terminal (SUCCEEDED) — the unique partial index on name treats
    QUEUED/RUNNING as "active", so creating the successor any earlier (e.g.
    from inside the handler, while its own row is still RUNNING) would
    always collide with itself, not just under a real race."""

    delay_seconds: float
    result: dict | None = None


FinancialJobResult = dict | Reschedule | None
FinancialJobHandler = Callable[[AsyncSession, dict], Awaitable[FinancialJobResult]]

_HANDLERS: dict[str, FinancialJobHandler] = {}


class UnknownFinancialJobError(KeyError):
    pass


def financial_job_handler(name: str) -> Callable[[FinancialJobHandler], FinancialJobHandler]:
    def decorator(handler: FinancialJobHandler) -> FinancialJobHandler:
        _HANDLERS[name] = handler
        return handler

    return decorator


def resolve_financial_handler(name: str) -> FinancialJobHandler:
    try:
        return _HANDLERS[name]
    except KeyError:
        raise UnknownFinancialJobError(name) from None


class FinancialWorker:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(), name="financial-worker")
            logger.info("Financial worker started (poll every %ss)", self._settings.market_check_interval_seconds)

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def run_forever(self) -> None:
        """Entry point for the standalone process (see __main__.py)."""
        self.start()
        await self._stopping.wait()

    async def _run(self) -> None:
        poll_interval = 5.0
        while not self._stopping.is_set():
            try:
                processed = await self.run_once()
            except Exception:  # noqa: BLE001 - the loop must survive anything
                logger.exception("Financial worker tick failed")
                processed = 0
            if processed == 0:
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=poll_interval)
                except asyncio.TimeoutError:
                    pass

    async def run_once(self) -> int:
        async with async_session_factory() as session:
            repository = FinancialJobRepository(session)
            now = datetime.now(timezone.utc)

            await self._recover_stale(session, repository, now)
            claimed = await self._claim_due(session, repository, now)
            job_ids = [job.id for job in claimed]

            for job_id in job_ids:
                async with async_session_factory() as job_session:
                    job_repository = FinancialJobRepository(job_session)
                    job = await job_repository.get(job_id)
                    if job is None:
                        continue
                    await self._execute(job_session, job_repository, job)

            return len(job_ids)

    async def _claim_due(
        self, session: AsyncSession, repository: FinancialJobRepository, now: datetime
    ) -> list[FinancialJob]:
        jobs = await repository.due_jobs(now, limit=10, for_update=True)
        for job in jobs:
            job.status = FinancialJobStatus.RUNNING
            job.started_at = now
            job.attempts += 1
        await session.commit()
        return jobs

    async def _recover_stale(
        self, session: AsyncSession, repository: FinancialJobRepository, now: datetime
    ) -> None:
        started_before = now - timedelta(seconds=300)
        for job in await repository.stale_running_jobs(started_before):
            logger.warning("Recovering stale financial job %s (%s), attempt %s", job.id, job.name, job.attempts)
            if job.attempts >= job.max_attempts:
                await repository.update(
                    job, status=FinancialJobStatus.FAILED, finished_at=now,
                    last_error="worker crashed or timed out while running the job",
                )
            else:
                await repository.update(job, status=FinancialJobStatus.QUEUED, scheduled_at=now)

    async def _execute(self, session: AsyncSession, repository: FinancialJobRepository, job: FinancialJob) -> None:
        job_id, job_name = job.id, job.name
        started = time.perf_counter()
        try:
            handler = resolve_financial_handler(job.name)
            result = await handler(session, dict(job.payload or {}))
        except Exception as exc:  # noqa: BLE001 - handler failures feed the retry logic
            await session.rollback()
            duration = time.perf_counter() - started
            logger.warning("Financial job %s (%s) failed after %.2fs: %s", job_id, job_name, duration, exc)
            job = await repository.get(job_id) or job
            await self._handle_failure(repository, job, exc)
            return

        duration = time.perf_counter() - started
        logger.info("Financial job %s (%s) succeeded in %.2fs", job_id, job_name, duration)
        reschedule = result if isinstance(result, Reschedule) else None
        await repository.update(
            job, status=FinancialJobStatus.SUCCEEDED, finished_at=datetime.now(timezone.utc),
            result=reschedule.result if reschedule else result,
        )
        if reschedule is not None:
            # Only now is the current row terminal — safe against the
            # unique partial index, which treats QUEUED/RUNNING as active.
            try:
                await repository.create(name=job_name, payload={}, delay_seconds=reschedule.delay_seconds)
            except DuplicateChainError:
                logger.debug("Reschedule for %s skipped: a chain is already queued/running", job_name)

    async def _handle_failure(self, repository: FinancialJobRepository, job: FinancialJob, exc: Exception) -> None:
        error = f"{type(exc).__name__}: {exc}"
        if job.attempts >= job.max_attempts:
            await repository.update(
                job, status=FinancialJobStatus.FAILED, finished_at=datetime.now(timezone.utc), last_error=error
            )
            return
        backoff = 30 * (2 ** (job.attempts - 1))
        # An exception carrying retry_after_seconds (e.g. Telegram's 429)
        # sets a floor on the delay — never retry sooner than the API itself
        # asked for, even if exponential backoff would be shorter.
        retry_after = getattr(exc, "retry_after_seconds", None)
        if retry_after is not None:
            backoff = max(backoff, retry_after)
        await repository.update(
            job, status=FinancialJobStatus.QUEUED,
            scheduled_at=datetime.now(timezone.utc) + timedelta(seconds=backoff), last_error=error,
        )


financial_worker = FinancialWorker()
