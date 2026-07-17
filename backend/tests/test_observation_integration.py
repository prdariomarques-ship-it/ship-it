"""End-to-end integration: Observation Scheduler seeds the durable chain,
a real API call (goal creation) triggers Event integration to pull the next
tick forward, the JobWorker processes it for real (no mocking), and the
resulting CurrentContext reflects what actually happened — proving the
Context Observation Engine's success criterion (the system always knows its
current state before deciding) end to end, plus restart-safety (a fresh
engine instance, simulating a process restart, is repopulated from the same
durable job chain without any special recovery code).

Same combined client + real JobWorker shape as
tests/test_whatsapp_pipeline.py::test_full_pipeline_webhook_to_reply.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from jobs.worker import JobWorker
from observation.engine import ContextObservationEngine, context_observation_engine
from observation.events import register_event_subscribers
from observation.scheduler import JOB_NAME, start as start_scheduler
from repositories.job import JobRepository
from repositories.user import UserRepository


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def worker(session_factory, monkeypatch):
    monkeypatch.setattr("jobs.worker.async_session_factory", session_factory)
    monkeypatch.setattr("observation.events.async_session_factory", session_factory)
    return JobWorker()


@pytest.fixture(autouse=True)
def _observation_wired():
    register_event_subscribers()
    context_observation_engine.reset()
    yield
    context_observation_engine.reset()


def _naive_to_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_scheduler_seed_to_first_snapshot(
    client, auth_headers, session_factory, worker
):
    # 1) App startup seeds the chain (main.py::lifespan calls this).
    async with session_factory() as session:
        await start_scheduler(session)
    async with session_factory() as session:
        seeded = await JobRepository(session).pending_by_name(JOB_NAME)
    assert seeded is not None

    # 2) The worker processes the first tick for real: builds a CurrentContext
    #    for the owner (the auth_headers fixture registered "dario@example.com",
    #    the first user, hence the instance's only admin/owner).
    assert await worker.run_once() == 1

    owner = await _get_owner(session_factory)
    snapshot = context_observation_engine.current(owner.id)
    assert snapshot is not None
    assert snapshot.trigger == "scheduler"

    # 3) Restart-safety: the tick re-queued its own next run before returning.
    async with session_factory() as session:
        next_tick = await JobRepository(session).pending_by_name(JOB_NAME)
    assert next_tick is not None
    assert next_tick.id != seeded.id


@pytest.mark.asyncio
async def test_goal_creation_pulls_the_next_tick_forward_and_shows_up_in_context(
    client, auth_headers, session_factory, worker
):
    async with session_factory() as session:
        await start_scheduler(session)
    await worker.run_once()  # first tick: baseline snapshot, no goals yet

    owner = await _get_owner(session_factory)
    assert context_observation_engine.current(owner.id).goals == []

    async with session_factory() as session:
        pending_before = await JobRepository(session).pending_by_name(JOB_NAME)
    far_future = datetime.now(timezone.utc) + timedelta(hours=1)
    async with session_factory() as session:
        job = await JobRepository(session).get(pending_before.id)
        job.scheduled_at = far_future
        await session.commit()

    # A real API call — not a synthetic event_bus.publish — creates a goal.
    response = await client.post(
        "/api/goals",
        json={"title": "Aprender violão", "priority": "high"},
        headers=auth_headers,
    )
    assert response.status_code == 201

    # Event integration (observation/events.py) reacted to goal.created and
    # pulled the pending tick back to "now".
    async with session_factory() as session:
        pulled = await JobRepository(session).pending_by_name(JOB_NAME)
    assert _naive_to_utc(pulled.scheduled_at) <= datetime.now(timezone.utc) + timedelta(
        seconds=2
    )

    # Processing that tick reflects the new goal in CurrentContext.
    async with session_factory() as session:
        job = await JobRepository(session).get(pulled.id)
        job.scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
    assert await worker.run_once() == 1

    snapshot = context_observation_engine.current(owner.id)
    assert any("Aprender violão" in item.content for item in snapshot.goals)
    assert any("goal" in item.content.lower() for item in snapshot.recent_events)


@pytest.mark.asyncio
async def test_a_fresh_engine_instance_is_repopulated_from_the_same_job_chain(
    client, auth_headers, session_factory, worker
):
    """Simulates a process restart: the cache is gone (a brand-new
    ContextObservationEngine has an empty dict), but the already-queued
    job — persisted in Postgres before the "crash" — is what makes the next
    tick happen without any special recovery logic, same guarantee
    JobWorker already provides for every other job (see jobs/worker.py's
    module docstring on stale-job recovery)."""
    async with session_factory() as session:
        await start_scheduler(session)
    owner = await _get_owner(session_factory)

    fresh_engine = ContextObservationEngine()
    assert fresh_engine.current(owner.id) is None

    import observation.scheduler as scheduler_module

    original = scheduler_module.context_observation_engine
    scheduler_module.context_observation_engine = fresh_engine
    try:
        assert await worker.run_once() == 1
    finally:
        scheduler_module.context_observation_engine = original

    assert fresh_engine.current(owner.id) is not None


async def _get_owner(session_factory):
    async with session_factory() as session:
        return await UserRepository(session).get_first_admin()
