"""Observation Scheduler (observation/scheduler.py): observation.tick is a
self-rescheduling job handler running on the existing JobWorker — no new
timer/loop primitive. Same fixture shape as tests/test_jobs.py (a real
JobWorker pointed at the test database via monkeypatch).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from jobs.service import JobService
from jobs.worker import JobWorker
from models.job import JobStatus
from models.user import User, UserRole
from observation.engine import context_observation_engine
from observation.scheduler import JOB_NAME, start
from repositories.job import JobRepository
from utils.config import get_settings


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def worker(session_factory, monkeypatch):
    monkeypatch.setattr("jobs.worker.async_session_factory", session_factory)
    return JobWorker()


@pytest.fixture(autouse=True)
def _reset_engine():
    context_observation_engine.reset()
    yield
    context_observation_engine.reset()


@pytest.fixture
async def owner(session_factory) -> User:
    async with session_factory() as session:
        user = User(
            email="owner@example.com",
            full_name="Dario",
            hashed_password="x",
            role=UserRole.ADMIN,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_tick_builds_context_for_the_owner(session_factory, worker, owner):
    async with session_factory() as session:
        await JobService(session).enqueue(JOB_NAME)

    assert await worker.run_once() == 1
    assert context_observation_engine.current(owner.id) is not None


@pytest.mark.asyncio
async def test_tick_reschedules_itself(session_factory, worker, owner):
    async with session_factory() as session:
        await JobService(session).enqueue(JOB_NAME)
    before = datetime.now(timezone.utc)

    await worker.run_once()

    async with session_factory() as session:
        queued = await JobRepository(session).list(status=JobStatus.QUEUED, limit=10)

    next_ticks = [job for job in queued if job.name == JOB_NAME]
    assert len(next_ticks) == 1
    scheduled_at = next_ticks[0].scheduled_at
    if scheduled_at.tzinfo is None:  # SQLite drops tzinfo on round-trip
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    expected_delay = get_settings().observation_interval_seconds
    actual_delay = (scheduled_at - before).total_seconds()
    assert actual_delay == pytest.approx(expected_delay, abs=5)


@pytest.mark.asyncio
async def test_tick_reschedules_even_with_no_admin_yet(session_factory, worker):
    async with session_factory() as session:
        await JobService(session).enqueue(JOB_NAME)

    assert await worker.run_once() == 1  # does not raise / does not fail the job

    async with session_factory() as session:
        job = (
            await JobRepository(session).list(status=JobStatus.QUEUED, limit=10)
        )
    assert any(j.name == JOB_NAME for j in job)


@pytest.mark.asyncio
async def test_start_seeds_the_first_tick(session_factory):
    async with session_factory() as session:
        await start(session)

    async with session_factory() as session:
        pending = await JobRepository(session).pending_by_name(JOB_NAME)
    assert pending is not None


@pytest.mark.asyncio
async def test_start_is_idempotent_when_a_tick_is_already_pending(session_factory):
    async with session_factory() as session:
        await start(session)
    async with session_factory() as session:
        await start(session)  # simulates a restart

    async with session_factory() as session:
        all_queued = await JobRepository(session).list(status=JobStatus.QUEUED, limit=50)
    assert sum(1 for job in all_queued if job.name == JOB_NAME) == 1


@pytest.mark.asyncio
async def test_start_does_nothing_when_observation_is_disabled(
    session_factory, monkeypatch
):
    monkeypatch.setattr(get_settings(), "observation_enabled", False)

    async with session_factory() as session:
        await start(session)

    async with session_factory() as session:
        pending = await JobRepository(session).pending_by_name(JOB_NAME)
    assert pending is None
