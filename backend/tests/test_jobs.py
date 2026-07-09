"""Durable job queue: enqueue, execution, retry with backoff, terminal failure."""
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
async def test_scheduled_job_not_picked_before_time(session_factory, worker):
    @job_handler("test.later")
    async def _later(db, payload):
        pass

    async with session_factory() as session:
        await JobService(session).enqueue("test.later", delay_seconds=3600)

    assert await worker.run_once() == 0


@pytest.mark.asyncio
async def test_jobs_api_enqueue_and_cancel(client, auth_headers):
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

    unknown = await client.post("/api/jobs", json={"name": "nope"}, headers=auth_headers)
    assert unknown.status_code == 422

    cancelled = await client.post(f"/api/jobs/{job_id}/cancel", headers=auth_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
