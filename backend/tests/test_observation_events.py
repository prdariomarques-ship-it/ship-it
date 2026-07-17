"""Event integration (observation/events.py): goal/job/agent activity pulls
the already-queued observation.tick forward instead of waiting for the next
scheduled run — the "event-driven" half of the Context Observation Engine
(the scheduler tick, tested in tests/test_observation_scheduler.py, is the
other half). Uses the real event_bus singleton, same as tests/test_goals.py's
EventBus assertions — the autouse `_reset_local_caches` fixture in
conftest.py already resets it (and re-registers subscribers per test via
`register_event_subscribers`, mirroring jobs.handlers' own pattern).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from events.bus import event_bus
from jobs.service import JobService
from observation.events import register_event_subscribers
from observation.scheduler import JOB_NAME
from repositories.job import JobRepository


@pytest.fixture
async def session_factory(db_engine, monkeypatch):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    # observation/events.py opens its own session via
    # database.session.async_session_factory — point that at the test db.
    monkeypatch.setattr("observation.events.async_session_factory", factory)
    return factory


@pytest.fixture(autouse=True)
def _subscribed():
    register_event_subscribers()
    yield


def _far_future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


@pytest.mark.asyncio
async def test_goal_event_pulls_a_pending_tick_forward(session_factory):
    async with session_factory() as session:
        job = await JobService(session).enqueue(
            JOB_NAME, delay_seconds=(_far_future() - datetime.now(timezone.utc)).total_seconds()
        )

    await event_bus.publish("goal.created", {"goal_id": 1, "user_id": 1})

    async with session_factory() as session:
        refreshed = await JobRepository(session).get(job.id)

    scheduled_at = refreshed.scheduled_at
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    assert scheduled_at <= datetime.now(timezone.utc) + timedelta(seconds=2)


@pytest.mark.asyncio
async def test_job_event_pulls_a_pending_tick_forward(session_factory):
    async with session_factory() as session:
        job = await JobService(session).enqueue(
            JOB_NAME, delay_seconds=3600
        )

    await event_bus.publish(
        "job.succeeded", {"job_id": 999, "job_name": "contact.summarize"}
    )

    async with session_factory() as session:
        refreshed = await JobRepository(session).get(job.id)
    scheduled_at = refreshed.scheduled_at
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    assert scheduled_at <= datetime.now(timezone.utc) + timedelta(seconds=2)


@pytest.mark.asyncio
async def test_agent_event_pulls_a_pending_tick_forward(session_factory):
    async with session_factory() as session:
        job = await JobService(session).enqueue(JOB_NAME, delay_seconds=3600)

    await event_bus.publish("agent.replied", {"agent": "assistant"})

    async with session_factory() as session:
        refreshed = await JobRepository(session).get(job.id)
    scheduled_at = refreshed.scheduled_at
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    assert scheduled_at <= datetime.now(timezone.utc) + timedelta(seconds=2)


@pytest.mark.asyncio
async def test_observation_ticks_own_job_events_do_not_retrigger_themselves(
    session_factory,
):
    async with session_factory() as session:
        job = await JobService(session).enqueue(JOB_NAME, delay_seconds=3600)
    original_scheduled_at = job.scheduled_at

    # observation.tick's own lifecycle event must be ignored, or every tick
    # would perpetually pull its own next run forward to "now".
    await event_bus.publish(
        "job.succeeded", {"job_id": job.id, "job_name": JOB_NAME}
    )

    async with session_factory() as session:
        refreshed = await JobRepository(session).get(job.id)
    assert refreshed.scheduled_at == original_scheduled_at


@pytest.mark.asyncio
async def test_unrelated_event_does_not_touch_the_pending_tick(session_factory):
    async with session_factory() as session:
        job = await JobService(session).enqueue(JOB_NAME, delay_seconds=3600)
    original_scheduled_at = job.scheduled_at

    await event_bus.publish("whatsapp.session_changed", {})

    async with session_factory() as session:
        refreshed = await JobRepository(session).get(job.id)
    assert refreshed.scheduled_at == original_scheduled_at


@pytest.mark.asyncio
async def test_no_pending_tick_is_a_no_op(session_factory):
    # No observation.tick queued (e.g. OBSERVATION_ENABLED=false) — must not
    # raise and must not create one; event integration reacts to the
    # scheduler's chain, it never starts one on its own.
    await event_bus.publish("goal.created", {"goal_id": 1, "user_id": 1})

    async with session_factory() as session:
        pending = await JobRepository(session).pending_by_name(JOB_NAME)
    assert pending is None
