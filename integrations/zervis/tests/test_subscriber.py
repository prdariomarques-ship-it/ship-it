import asyncio
import json

import pytest

from zervis_bridge.buffer import EventBuffer
from zervis_bridge.subscriber import EventSubscriber


def msg(name, payload):
    return json.dumps(
        {"name": name, "payload": payload, "occurred_at": "2026-10-17T00:00:00+00:00"}
    )


def test_handle_sanitizes_and_counts_drops():
    buf = EventBuffer(10, 60)
    sub = EventSubscriber("redis://x", "ch", buf)
    sub.handle(msg("job.failed", {"job_id": 1, "job_payload": {"phone": "+55"}}))
    sub.handle(msg("admin.setting_updated", {"key": "k", "value": "secret"}))
    sub.handle("not json")
    sub.handle(None)
    events = buf.since(0)["events"]
    assert len(events) == 1 and events[0]["payload"] == {"job_id": 1}
    assert sub.dropped == 3


class FakePubSub:
    def __init__(self, messages, fail_after=False):
        self._messages = messages
        self._fail = fail_after

    async def subscribe(self, channel):
        self.channel = channel

    async def listen(self):
        for data in self._messages:
            yield {"type": "message", "data": data}
        if self._fail:
            raise ConnectionError("reset")


class FakeRedis:
    def __init__(self, pubsub):
        self._pubsub = pubsub
        self.closed = False

    def pubsub(self, **kwargs):
        return self._pubsub

    async def aclose(self):
        self.closed = True


async def test_run_reconnects_after_failure_and_keeps_collecting(monkeypatch):
    real_sleep = asyncio.sleep

    async def fast_sleep(_):
        await real_sleep(0)

    monkeypatch.setattr("zervis_bridge.subscriber.asyncio.sleep", fast_sleep)
    buf = EventBuffer(10, 60)
    clients = [
        FakeRedis(FakePubSub([msg("job.done", {"job_id": 1})], fail_after=True)),
        FakeRedis(FakePubSub([msg("job.done", {"job_id": 2})], fail_after=True)),
    ]
    made = []

    def factory(url):
        client = clients[len(made)] if len(made) < len(clients) else clients[-1]
        made.append(client)
        return client

    sub = EventSubscriber("redis://x", "ch", buf, client_factory=factory)
    task = asyncio.create_task(sub.run())
    for _ in range(50):
        await asyncio.sleep(0)
        if len(made) >= 3:
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    ids = [e["payload"]["job_id"] for e in buf.since(0)["events"]]
    assert ids[:2] == [1, 2]
    assert all(c.closed for c in clients)
    assert sub.connected is False
