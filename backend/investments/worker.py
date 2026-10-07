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
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from database.session import async_session_factory
from investments.models import CHAIN_JOB_NAMES, FinancialJob, FinancialJobStatus
from investments.repository import DuplicateChainError, FinancialJobRepository
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


async def ensure_chains_seeded(repository: FinancialJobRepository, enabled: bool) -> None:
    """Create the first/missing row for each self-rescheduling chain name.
    Idempotent: a DuplicateChainError (a chain is already QUEUED/RUNNING)
    is expected and dropped, not an error.

    Called both once at process start AND on every worker tick (see
    FinancialWorker.run_once) as a backstop for the case where a whole
    process dies before even claiming a job (so no row, successor or
    otherwise, was ever written) — the normal successful-completion path
    no longer has a gap here at all: see
    FinancialJobRepository.complete_and_reschedule, which marks a chain's
    current row SUCCEEDED and creates its successor in ONE transaction, so
    "terminal but no successor" is never a committed, observable state for
    another process's healing pass to react to. This no-successor case is
    reseeded immediately (delay_seconds=0) rather than waiting out the
    full cadence — a legitimate catch-up after an unexplained gap, not a
    race with the normal cadence."""
    if not enabled:
        return
    for name in CHAIN_JOB_NAMES:
        try:
            await repository.create(name=name, payload={})
            logger.info("Seeded/healed financial monitor chain %s", name)
        except DuplicateChainError:
            pass


@dataclass
class Reschedule:
    """A handler returns this instead of a plain result dict to re-arm its
    own chain. The worker applies it (via complete_and_reschedule) in the
    SAME transaction that marks the current row SUCCEEDED — never two
    separate commits, so there is no window where another process could
    observe "terminal, no successor yet" and react to it."""

    delay_seconds: float
    result: dict | None = None


FinancialJobResult = dict | Reschedule | None
FinancialJobHandler = Callable[[AsyncSession, FinancialJob], Awaitable[FinancialJobResult]]

_HANDLERS: dict[str, FinancialJobHandler] = {}

# Job names whose handler has an external, irreversible side effect (sends
# a real message to a real person). If the worker process crashes between
# the handler returning (meaning Telegram may have already accepted and
# delivered the message) and the result being persisted, stale-RUNNING
# recovery must NEVER silently requeue one of these for another attempt —
# that would risk sending the same message twice. It is instead marked
# FAILED with an explicit uncertain-outcome result, for a human to check.
AT_MOST_ONCE_JOB_NAMES = {"telegram.send_message"}


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


# Written after every tick, successful or not — on its own this proves only
# that the loop is alive (liveness), not that anything is actually working
# (readiness) — see _write_heartbeat and docker-compose.financial.yml's
# healthcheck, which checks both the file's age and its health_ok field.
# This process has no HTTP server to poll (see __main__.py), hence a file.
HEARTBEAT_PATH = "/tmp/financial_worker_heartbeat"
# Liveness is "the loop is still ticking"; readiness folds in whether the
# last tick could actually talk to the database and how many ticks in a
# row have failed outright — a looping-but-broken process (e.g. DB
# unreachable) must not report the same "healthy" as a looping-and-working
# one. Still a single combined signal in one file: Docker's HEALTHCHECK has
# no separate liveness/readiness probe types the way Kubernetes does: a
# real split would need either two files polled by two different checks,
# or an actual embedded HTTP server — deferred, not built here, since it
# would require adding the HTTP surface this package has deliberately
# avoided (see module docstring).
CONSECUTIVE_FAILURE_THRESHOLD = 5


class FinancialWorker:
    def __init__(self, heartbeat_path: str = HEARTBEAT_PATH) -> None:
        self._settings = get_settings()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._heartbeat_path = heartbeat_path
        self._consecutive_tick_failures = 0

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
            db_ok = True
            try:
                processed = await self.run_once()
                self._consecutive_tick_failures = 0
            except Exception as exc:  # noqa: BLE001 - the loop must survive anything
                logger.exception("Financial worker tick failed")
                processed = 0
                db_ok = False
                self._consecutive_tick_failures += 1
            self._write_heartbeat(db_ok=db_ok)
            if processed == 0:
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=poll_interval)
                except asyncio.TimeoutError:
                    pass

    def _write_heartbeat(self, db_ok: bool) -> None:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "db_ok": db_ok,
            "consecutive_tick_failures": self._consecutive_tick_failures,
            "healthy": db_ok and self._consecutive_tick_failures < CONSECUTIVE_FAILURE_THRESHOLD,
        }
        try:
            with open(self._heartbeat_path, "w") as f:
                json.dump(payload, f)
        except OSError:
            logger.warning("Could not write heartbeat file %s", self._heartbeat_path)

    async def run_once(self) -> int:
        async with async_session_factory() as session:
            repository = FinancialJobRepository(session)
            now = datetime.now(timezone.utc)

            await self._recover_stale(repository, now)
            await ensure_chains_seeded(repository, self._settings.market_monitors_enabled)
            claimed = await repository.claim_due(now, limit=10)
            job_ids = [job.id for job in claimed]

            for job_id in job_ids:
                async with async_session_factory() as job_session:
                    job_repository = FinancialJobRepository(job_session)
                    job = await job_repository.get(job_id)
                    if job is None:
                        continue
                    await self._execute(job_repository, job)

            return len(job_ids)

    async def _recover_stale(self, repository: FinancialJobRepository, now: datetime) -> None:
        for job in await repository.stale_running_candidates(now):
            logger.warning("Recovering stale financial job %s (%s), attempt %s", job.id, job.name, job.attempts)
            if job.name in AT_MOST_ONCE_JOB_NAMES:
                recovered = await repository.try_recover_stale(
                    job.id, job.lease_token, now, failed=True,
                    last_error="Recovered from a stale RUNNING state: the handler may have already "
                               "completed (e.g. Telegram may have already accepted the message) before "
                               "the crash — not auto-retried to avoid a possible duplicate send.",
                    result={"delivered": None, "reason": "uncertain_outcome_process_crash"},
                )
            elif job.attempts >= job.max_attempts:
                recovered = await repository.try_recover_stale(
                    job.id, job.lease_token, now, failed=True,
                    last_error="worker crashed or timed out while running the job",
                )
            else:
                recovered = await repository.try_recover_stale(
                    job.id, job.lease_token, now, failed=False,
                    last_error="worker crashed or timed out while running the job (requeued)",
                )
            if not recovered:
                # Another process's recovery pass (or this job's own slow-
                # but-legitimate execution finishing normally) already
                # changed this row between our read and this UPDATE — not
                # an error, just means we lost the race and must not act
                # on stale information.
                logger.debug("Recovery for job %s no-op: lease already changed by someone else", job.id)

    async def _execute(self, repository: FinancialJobRepository, job: FinancialJob) -> None:
        # Captured as locals, not read off `job` again after this point:
        # session.rollback() (below, on the exception path) expires every
        # ORM instance in the session by default, so a later `job.attempts`
        # attribute access would trigger an implicit lazy-reload — which
        # needs an async context SQLAlchemy's sync attribute-access path
        # doesn't have here, raising MissingGreenlet. Confirmed by
        # reproducing it before this fix.
        job_id, job_name, lease_token = job.id, job.name, job.lease_token
        attempts, max_attempts = job.attempts, job.max_attempts
        started = time.perf_counter()
        try:
            handler = resolve_financial_handler(job.name)
            result = await handler(repository.session, job)
        except Exception as exc:  # noqa: BLE001 - handler failures feed the retry logic
            await repository.session.rollback()
            duration = time.perf_counter() - started
            logger.warning("Financial job %s (%s) failed after %.2fs: %s", job_id, job_name, duration, exc)
            backoff = 30 * (2 ** (attempts - 1))
            retry_after = getattr(exc, "retry_after_seconds", None)
            if retry_after is not None:
                backoff = max(backoff, retry_after)
            owned = await repository.retry_or_fail_if_owner(
                job_id, lease_token, attempts=attempts, max_attempts=max_attempts,
                backoff_seconds=backoff, error=f"{type(exc).__name__}: {exc}",
            )
            if not owned:
                logger.warning(
                    "Job %s (%s) finished (with error) after its lease was reclaimed — "
                    "result discarded, the new owner's state was not touched.", job_id, job_name,
                )
            return

        duration = time.perf_counter() - started
        logger.info("Financial job %s (%s) succeeded in %.2fs", job_id, job_name, duration)
        reschedule = result if isinstance(result, Reschedule) else None
        finished_at = datetime.now(timezone.utc)

        if reschedule is not None:
            completed, rescheduled = await repository.complete_and_reschedule(
                job_id, lease_token, result=reschedule.result, finished_at=finished_at,
                reschedule_name=job_name, reschedule_delay_seconds=reschedule.delay_seconds,
            )
            if not completed:
                logger.warning(
                    "Job %s (%s) completed after its lease was reclaimed — "
                    "result discarded, no successor created by this execution.", job_id, job_name,
                )
            elif not rescheduled:
                logger.debug("Job %s (%s): chain already had an active successor.", job_id, job_name)
        else:
            completed = await repository.complete_if_owner(
                job_id, lease_token, status=FinancialJobStatus.SUCCEEDED, finished_at=finished_at, result=result
            )
            if not completed:
                logger.warning(
                    "Job %s (%s) completed after its lease was reclaimed — result discarded.", job_id, job_name
                )


financial_worker = FinancialWorker()
