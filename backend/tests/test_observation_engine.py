"""Context Observation Engine (observation/engine.py): caches the latest
CurrentContext per user in memory, rebuilds via ObservationContextBuilder,
and publishes observation.context_updated on the Event Bus. Fresh instances
throughout (mirrors tests/test_events.py::EventBus() and
tests/test_jobs.py::JobWorker() — never the module-level singleton), so
tests never depend on the per-test event bus/singleton reset ordering.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from events.bus import EventBus
from models.user import User
from observation.engine import ContextObservationEngine


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def user(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="engine@example.com", full_name="Dario", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_current_is_none_before_the_first_observation(user):
    engine = ContextObservationEngine()
    assert engine.current(user.id) is None


@pytest.mark.asyncio
async def test_observe_populates_the_cache(session_factory, user):
    engine = ContextObservationEngine()
    async with session_factory() as session:
        built = await engine.observe(session, user)

    cached = engine.current(user.id)
    assert cached is not None
    assert cached is built
    assert cached.user_id == user.id


@pytest.mark.asyncio
async def test_observe_publishes_context_updated_on_the_event_bus(
    session_factory, user, monkeypatch
):
    bus = EventBus()
    monkeypatch.setattr("observation.engine.event_bus", bus)

    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("observation.context_updated", handler)

    engine = ContextObservationEngine()
    async with session_factory() as session:
        await engine.observe(session, user, trigger="startup")

    assert len(received) == 1
    assert received[0].payload["user_id"] == user.id
    assert received[0].payload["trigger"] == "startup"


@pytest.mark.asyncio
async def test_is_stale_true_with_no_snapshot(user):
    engine = ContextObservationEngine()
    assert engine.is_stale(user.id, max_age_seconds=60) is True


@pytest.mark.asyncio
async def test_is_stale_false_right_after_observe(session_factory, user):
    engine = ContextObservationEngine()
    async with session_factory() as session:
        await engine.observe(session, user)

    assert engine.is_stale(user.id, max_age_seconds=60) is False


@pytest.mark.asyncio
async def test_reset_clears_cached_snapshots(session_factory, user):
    engine = ContextObservationEngine()
    async with session_factory() as session:
        await engine.observe(session, user)
    assert engine.current(user.id) is not None

    engine.reset()
    assert engine.current(user.id) is None


@pytest.mark.asyncio
async def test_observe_scopes_snapshots_per_user(session_factory, user):
    async with session_factory() as session:
        other = User(email="other@example.com", full_name="Outro", hashed_password="x")
        session.add(other)
        await session.commit()
        await session.refresh(other)

    engine = ContextObservationEngine()
    async with session_factory() as session:
        await engine.observe(session, user)
    async with session_factory() as session:
        await engine.observe(session, other)

    assert engine.current(user.id).user_id == user.id
    assert engine.current(other.id).user_id == other.id
