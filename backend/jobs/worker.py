"""Async job worker: polls the durable queue, executes handlers, retries with
exponential backoff and emits lifecycle events.

Concurrency-safe by design:
- Due jobs are claimed with SELECT ... FOR UPDATE SKIP LOCKED and flipped to
  RUNNING in a single transaction, so multiple worker processes (API replicas
  or dedicated workers) never execute the same job twice.
- A handler failure rolls the session back before recording the retry, so a
  half-written transaction can never be committed by the bookkeeping.
- Jobs stuck in RUNNING (worker crashed mid-flight) are recovered on each tick:
  requeued while attempts remain, failed otherwise.
"""
import asyncio
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from database.session import async_session_factory
from jobs.events import job_event_publisher
from jobs.registry import resolve_handler
from models.job import Job, JobStatus
from observability.metrics import record_job_duration
from repositories.job import JobRepository
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class JobWorker:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._semaphore = asyncio.Semaphore(self._settings.jobs_max_concurrent_workers)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(), name="job-worker")
            logger.info("Job worker started (poll every %ss)", self._settings.jobs_poll_interval_seconds)

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                processed = await self.run_once()
            except Exception:  # noqa: BLE001 - the worker loop must survive anything
                logger.exception("Job worker tick failed")
                processed = 0
            if processed == 0:
                try:
                    await asyncio.wait_for(
                        self._stopping.wait(), timeout=self._settings.jobs_poll_interval_seconds
                    )
                except asyncio.TimeoutError:
                    pass

    async def run_once(self) -> int:
        """Recover stale jobs and process one batch of due jobs. Returns batch size."""
        async with async_session_factory() as session:
            repository = JobRepository(session)
            now = datetime.now(timezone.utc)

            await self._recover_stale(session, repository, now)
            claimed = await self._claim_due(session, repository, now)
            # Capture ids while the objects are guaranteed fresh (just
            # committed above). Each concurrent job needs its own session to avoid
            # SQLAlchemy async concurrency issues (session is not thread-safe).
            job_ids = [job.id for job in claimed]

            async def execute_with_semaphore(job_id: int) -> None:
                async with self._semaphore:
                    # Each job gets its own session and repository to avoid
                    # concurrent access to the same session state.
                    async with async_session_factory() as job_session:
                        job_repository = JobRepository(job_session)
                        job = await job_repository.get(job_id)
                        if job is None:
                            return
                        await self._execute(job_session, job_repository, job)

            if job_ids:
                await asyncio.gather(*(execute_with_semaphore(job_id) for job_id in job_ids))

            return len(job_ids)

    async def _claim_due(
        self, session: AsyncSession, repository: JobRepository, now: datetime
    ) -> list[Job]:
        """Atomically flip a batch of due jobs to RUNNING (multi-worker safe)."""
        jobs = await repository.due_jobs(now, limit=10, for_update=True)
        for job in jobs:
            job.status = JobStatus.RUNNING
            job.started_at = now
            job.attempts += 1
        await session.commit()
        return jobs

    async def _recover_stale(
        self, session: AsyncSession, repository: JobRepository, now: datetime
    ) -> None:
        started_before = now - timedelta(seconds=self._settings.jobs_stale_after_seconds)
        for job in await repository.stale_running_jobs(started_before):
            logger.warning("Recovering stale job %s (%s), attempt %s", job.id, job.name, job.attempts)
            if job.attempts >= job.max_attempts:
                await repository.update(
                    job,
                    status=JobStatus.FAILED,
                    finished_at=now,
                    last_error="worker crashed or timed out while running the job",
                )
                await job_event_publisher.publish(session, job, "failed", detail="stale job")
            else:
                await repository.update(job, status=JobStatus.QUEUED, scheduled_at=now)
                await job_event_publisher.publish(session, job, "retry_scheduled", detail="stale job")

    async def _execute(self, session: AsyncSession, repository: JobRepository, job: Job) -> None:
        await job_event_publisher.publish(session, job, "started")
        job_id, job_name = job.id, job.name
        started = time.perf_counter()

        try:
            handler = resolve_handler(job.name)
            await handler(session, dict(job.payload or {}))
        except Exception as exc:  # noqa: BLE001 - handler failures feed the retry logic
            # Discard whatever the failed handler left in the session before
            # recording the retry, or half-written changes would be committed.
            await session.rollback()
            record_job_duration(job_name, time.perf_counter() - started)
            job = await repository.get(job_id) or job
            await self._handle_failure(session, repository, job, exc)
            return

        record_job_duration(job_name, time.perf_counter() - started)
        await repository.update(job, status=JobStatus.SUCCEEDED, finished_at=datetime.now(timezone.utc))
        await job_event_publisher.publish(session, job, "succeeded")

    async def _handle_failure(
        self, session: AsyncSession, repository: JobRepository, job: Job, exc: Exception
    ) -> None:
        error = f"{type(exc).__name__}: {exc}"
        logger.warning("Job %s (%s) attempt %s failed: %s", job.id, job.name, job.attempts, error)

        if job.attempts >= job.max_attempts:
            await repository.update(
                job,
                status=JobStatus.FAILED,
                finished_at=datetime.now(timezone.utc),
                last_error=error,
            )
            await job_event_publisher.publish(session, job, "failed", detail=error)
            return

        backoff = self._settings.jobs_retry_backoff_seconds * (2 ** (job.attempts - 1))
        await repository.update(
            job,
            status=JobStatus.QUEUED,
            scheduled_at=datetime.now(timezone.utc) + timedelta(seconds=backoff),
            last_error=error,
        )
        await job_event_publisher.publish(session, job, "retry_scheduled", detail=error)


job_worker = JobWorker()
