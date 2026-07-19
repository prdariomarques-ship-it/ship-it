"""Durable job queue: enqueue, execution, retry with backoff, terminal failure."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from jobs.registry import _HANDLERS, job_handler
from jobs.service import JobService
from jobs.worker import JobWorker
from models.job import JobStatus


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def worker(session_factory, monkeypatch):
    monkeypatch.setattr("jobs.worker.async_session_factory", session_factory)
    return JobWorker()


@pytest.fixture(autouse=True)
def _isolated_handlers():
    saved = dict(_HANDLERS)
    yield
    _HANDLERS.clear()
    _HANDLERS.update(saved)


@pytest.mark.asyncio
async def test_job_succeeds(session_factory, worker):
    ran: list[dict] = []

    @job_handler("test.ok")
    async def _ok(db, payload):
        ran.append(payload)

    async with session_factory() as session:
        job = await JobService(session).enqueue("test.ok", {"x": 1})

    assert await worker.run_once() == 1
    assert ran == [{"x": 1}]

    async with session_factory() as session:
        refreshed = await session.get(type(job), job.id)
        assert refreshed.status == JobStatus.SUCCEEDED
        assert refreshed.attempts == 1
        assert refreshed.finished_at is not None


@pytest.mark.asyncio
async def test_job_retries_then_fails(session_factory, worker):
    @job_handler("test.boom")
    async def _boom(db, payload):
        raise RuntimeError("explode")

    async with session_factory() as session:
        job = await JobService(session).enqueue("test.boom", max_attempts=2)

    # Attempt 1: fails, rescheduled with backoff.
    await worker.run_once()
    async with session_factory() as session:
        refreshed = await session.get(type(job), job.id)
        assert refreshed.status == JobStatus.QUEUED
        assert refreshed.attempts == 1
        assert "explode" in refreshed.last_error

        # Pull the retry forward so the next tick picks it up.
        refreshed.scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    # Attempt 2: exhausts max_attempts -> failed.
    await worker.run_once()
    async with session_factory() as session:
        refreshed = await session.get(type(job), job.id)
        assert refreshed.status == JobStatus.FAILED
        assert refreshed.attempts == 2


@pytest.mark.asyncio
async def test_stale_running_job_is_requeued(session_factory, worker):
    from models.job import Job

    async with session_factory() as session:
        stale = Job(
            name="test.stale",
            status=JobStatus.RUNNING,
            attempts=1,
            max_attempts=3,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scheduled_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        session.add(stale)
        await session.commit()
        stale_id = stale.id

    @job_handler("test.stale")
    async def _stale(db, payload):
        pass

    # First tick recovers it to QUEUED; it then runs on the same tick's claim.
    await worker.run_once()
    async with session_factory() as session:
        refreshed = await session.get(Job, stale_id)
        assert refreshed.status == JobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_stale_job_with_exhausted_attempts_fails(session_factory, worker):
    from models.job import Job

    async with session_factory() as session:
        stale = Job(
            name="test.stale-dead",
            status=JobStatus.RUNNING,
            attempts=3,
            max_attempts=3,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scheduled_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        session.add(stale)
        await session.commit()
        stale_id = stale.id

    await worker.run_once()
    async with session_factory() as session:
        refreshed = await session.get(Job, stale_id)
        assert refreshed.status == JobStatus.FAILED
        assert "crashed" in refreshed.last_error


@pytest.mark.asyncio
async def test_failed_handler_changes_are_rolled_back(session_factory, worker):
    """A handler that dirties the session and raises must not leak partial writes."""
    from sqlalchemy import select

    from models.log import LogEntry

    @job_handler("test.dirty")
    async def _dirty(db, payload):
        db.add(LogEntry(source="dirty-handler", message="must not persist"))
        raise RuntimeError("explode after dirtying the session")

    async with session_factory() as session:
        job = await JobService(session).enqueue("test.dirty", max_attempts=1)

    await worker.run_once()

    async with session_factory() as session:
        refreshed = await session.get(type(job), job.id)
        assert refreshed.status == JobStatus.FAILED

        leaked = (
            (
                await session.execute(
                    select(LogEntry).where(LogEntry.source == "dirty-handler")
                )
            )
            .scalars()
            .all()
        )
        assert leaked == []


@pytest.mark.asyncio
async def test_scheduled_job_not_picked_before_time(session_factory, worker):
    @job_handler("test.later")
    async def _later(db, payload):
        pass

    async with session_factory() as session:
        await JobService(session).enqueue("test.later", delay_seconds=3600)

    assert await worker.run_once() == 0


@pytest.mark.asyncio
async def test_unknown_handler_fails_job_gracefully(session_factory, worker):
    """JobService.enqueue never validates the name against the registry (only
    the HTTP API does, at the router level) -- a job can end up queued for a
    name whose handler was since removed or renamed mid-deploy. resolve_handler
    raising UnknownJobError must be handled like any other handler failure
    (recorded via the normal retry/failure bookkeeping), not an unhandled
    exception that skips repository updates and kills the tick."""
    async with session_factory() as session:
        job = await JobService(session).enqueue("test.no-such-handler", max_attempts=1)

    assert await worker.run_once() == 1

    async with session_factory() as session:
        refreshed = await session.get(type(job), job.id)
        assert refreshed.status == JobStatus.FAILED
        assert "No handler registered" in refreshed.last_error


@pytest.mark.asyncio
async def test_worker_loop_survives_a_failing_tick(worker, monkeypatch):
    """The background poll loop (JobWorker._run) must log and continue on the
    next tick instead of dying when run_once raises unexpectedly -- otherwise
    a single bad tick (e.g. a transient DB outage) would silently stop all job
    processing until the whole process is restarted. This is the actual
    fault-tolerant/restart-resilient contract of the runtime's Scheduler."""
    import asyncio

    monkeypatch.setattr(worker._settings, "jobs_poll_interval_seconds", 0)
    calls: list[int] = []

    async def _flaky_run_once():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("tick blew up")
        worker._stopping.set()
        return 0

    monkeypatch.setattr(worker, "run_once", _flaky_run_once)
    await asyncio.wait_for(worker._run(), timeout=5)

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_handler_exceeding_execution_timeout_is_retried_not_left_hanging(
    session_factory, worker, monkeypatch
):
    """Root cause of the duplicate-execution bug this guards against: with
    no per-job execution ceiling, a handler slower than
    jobs_stale_after_seconds could be reclaimed by stale-job recovery and
    executed a second time concurrently while the first attempt was still
    genuinely running (e.g. a hung LLM/HTTP call). This proves the handler
    is cut off well before that point: run_once() must return promptly —
    bounded by the short timeout configured below, not by the handler's
    full sleep — and the job must come back QUEUED for retry with clear
    evidence of why, exactly like any other handler failure."""
    monkeypatch.setattr(worker._settings, "jobs_execution_timeout_seconds", 0.05)

    ran_to_completion = []

    @job_handler("test.hangs")
    async def _hangs(db, payload):
        await asyncio.sleep(10)  # far longer than the configured timeout
        ran_to_completion.append(True)  # must never be reached

    async with session_factory() as session:
        job = await JobService(session).enqueue("test.hangs", max_attempts=2)

    # A second, independent guard: if the timeout somehow didn't cut the
    # handler off, this would hang for ~10s instead of returning quickly.
    await asyncio.wait_for(worker.run_once(), timeout=5)

    assert ran_to_completion == []
    async with session_factory() as session:
        refreshed = await session.get(type(job), job.id)
        assert refreshed.status == JobStatus.QUEUED
        assert refreshed.attempts == 1
        assert "TimeoutError" in refreshed.last_error
        assert "execution limit" in refreshed.last_error

    # The persisted job-event log (jobs/events.py, queried via /admin/logs in
    # production) must make a global timeout distinguishable at a glance from
    # a stale-job recovery -- same "retry_scheduled" event, but a different
    # detail: an exception message here, versus the literal "stale job" that
    # _recover_stale always writes.
    from sqlalchemy import select

    from models.log import LogEntry

    async with session_factory() as session:
        entries = (
            (
                await session.execute(
                    select(LogEntry).where(LogEntry.source == "job:test.hangs")
                )
            )
            .scalars()
            .all()
        )
    details = [entry.payload.get("detail", "") for entry in entries]
    assert any("execution limit" in detail for detail in details)
    assert not any(detail == "stale job" for detail in details)


@pytest.mark.asyncio
async def test_execution_timeout_must_stay_below_stale_threshold(monkeypatch):
    """The fix depends entirely on this ordering — jobs_execution_timeout_seconds
    must always resolve a job's status before jobs_stale_after_seconds could
    otherwise reclaim it. A misconfiguration that violates this would
    silently reopen the exact race this fix closes, so it fails fast at
    construction instead."""
    from utils.config import Settings

    bad_settings = Settings()
    bad_settings.jobs_execution_timeout_seconds = 300
    bad_settings.jobs_stale_after_seconds = 300
    monkeypatch.setattr("jobs.worker.get_settings", lambda: bad_settings)

    with pytest.raises(AssertionError):
        JobWorker()


@pytest.mark.asyncio
async def test_jobs_api_enqueue(client, auth_headers):
    @job_handler("test.api")
    async def _api(db, payload):
        pass

    created = await client.post(
        "/api/jobs",
        json={"name": "test.api", "payload": {"a": 1}, "delay_seconds": 3600},
        headers=auth_headers,
    )
    assert created.status_code == 201
    job_id = created.json()["id"]

    unknown = await client.post(
        "/api/jobs", json={"name": "nope"}, headers=auth_headers
    )
    assert unknown.status_code == 422

    listed = await client.get("/api/jobs", headers=auth_headers)
    assert listed.status_code == 200
    assert any(job["id"] == job_id for job in listed.json())
