"""Event Bus: in-process pub/sub, wildcard subscriptions, handler isolation."""

from unittest.mock import AsyncMock, patch

import pytest

from events.bus import EventBus


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.mark.asyncio
async def test_publish_delivers_to_exact_subscriber(bus):
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("agent.replied", handler)
    await bus.publish("agent.replied", {"agent": "assistant"})

    assert len(received) == 1
    assert received[0].name == "agent.replied"
    assert received[0].payload == {"agent": "assistant"}


@pytest.mark.asyncio
async def test_subscriber_for_a_different_event_is_not_called(bus):
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("agent.replied", handler)
    await bus.publish("agent.selected", {})

    assert received == []


@pytest.mark.asyncio
async def test_wildcard_subscriber_receives_domain_events(bus):
    received = []

    async def handler(event):
        received.append(event.name)

    bus.subscribe("job.*", handler)
    await bus.publish("job.started", {})
    await bus.publish("job.succeeded", {})
    await bus.publish("agent.selected", {})  # different domain, must not match

    assert received == ["job.started", "job.succeeded"]


@pytest.mark.asyncio
async def test_no_subscribers_is_not_an_error(bus):
    event = await bus.publish("nothing.listens", {"x": 1})
    assert event.payload == {"x": 1}


@pytest.mark.asyncio
async def test_one_failing_handler_does_not_block_others(bus):
    received = []

    async def failing(event):
        raise RuntimeError("boom")

    async def working(event):
        received.append(event.name)

    bus.subscribe("thing.happened", failing)
    bus.subscribe("thing.happened", working)

    await bus.publish("thing.happened", {})
    assert received == ["thing.happened"]


@pytest.mark.asyncio
async def test_event_carries_occurred_at_timestamp(bus):
    event = await bus.publish("x.y", {})
    assert event.occurred_at is not None


@pytest.mark.asyncio
async def test_multiple_handlers_for_same_event_all_run(bus):
    received = []

    async def first(event):
        received.append("first")

    async def second(event):
        received.append("second")

    bus.subscribe("thing.happened", first)
    bus.subscribe("thing.happened", second)
    await bus.publish("thing.happened", {})

    assert received == ["first", "second"]


@pytest.mark.asyncio
async def test_publish_survives_redis_being_unavailable(bus):
    """In-process delivery must never depend on Redis fan-out succeeding."""
    received = []

    async def handler(event):
        received.append(event.name)

    bus.subscribe("thing.happened", handler)

    with patch(
        "events.bus.aioredis.from_url", side_effect=ConnectionError("redis down")
    ):
        event = await bus.publish("thing.happened", {})

    assert received == ["thing.happened"]
    assert event.name == "thing.happened"
    assert bus._redis_available is False


@pytest.mark.asyncio
async def test_redis_failure_is_not_retried_on_every_publish(bus):
    """Once Redis is marked unavailable, subsequent publishes must not
    attempt a new connection on every call — that would turn a down Redis
    into a per-request latency/error source instead of a one-time detection."""
    connect_attempts = 0

    def _from_url(*args, **kwargs):
        nonlocal connect_attempts
        connect_attempts += 1
        raise ConnectionError("redis down")

    with patch("events.bus.aioredis.from_url", side_effect=_from_url):
        await bus.publish("a.b", {})
        await bus.publish("a.b", {})
        await bus.publish("a.b", {})

    assert connect_attempts == 1


@pytest.mark.asyncio
async def test_publish_fans_out_to_redis_when_available(bus):
    mock_redis = AsyncMock()
    with patch("events.bus.aioredis.from_url", return_value=mock_redis):
        event = await bus.publish("agent.replied", {"agent": "assistant"})

    mock_redis.publish.assert_awaited_once()
    channel, payload = mock_redis.publish.call_args.args
    assert channel == bus._settings.events_channel
    assert event.name == "agent.replied"
