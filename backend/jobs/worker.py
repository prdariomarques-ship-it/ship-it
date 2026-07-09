"""Async job worker: polls the durable queue, executes handlers, retries with
exponential backoff and emits lifecycle events.

Runs inside the API process (started in the lifespan); because the queue is
Postgres-backed, additional worker processes can be added later without
changing the enqueue side.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from database.session import async_session_factory
from jobs.events import job_event_publisher
from jobs.registry import resolve_handler
from models.job import Job, JobStatus
from repositories.job import JobRepository
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class JobWorker:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

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
        """Process one batch of due jobs. Returns how many jobs ran."""
        async with async_session_factory() as session:
            repository = JobRepository(session)
            due = await repository.due_jobs(datetime.now(timezone.utc), limit=10)
            for job in due:
                await self._execute(session, repository, job)
            return len(due)

    async def _execute(self, session, repository: JobRepository, job: Job) -> None:
        now = datetime.now(timezone.utc)
        await repository.update(
            job, status=JobStatus.RUNNING, started_at=now, attempts=job.attempts + 1
        )
        await job_event_publisher.publish(session, job, "started")

        try:
            handler = resolve_handler(job.name)
            await handler(session, dict(job.payload or {}))
        except Exception as exc:  # noqa: BLE001 - handler failures feed the retry logic
            await self._handle_failure(session, repository, job, exc)
            return

        await repository.update(job, status=JobStatus.SUCCEEDED, finished_at=datetime.now(timezone.utc))
        await job_event_publisher.publish(session, job, "succeeded")

    async def _handle_failure(self, session, repository: JobRepository, job: Job, exc: Exception) -> None:
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
