"""Internal Event Bus: the one channel modules use to talk without importing
each other.

Two audiences, one `publish` call:
- **In-process subscribers** (`subscribe`) run inside this API instance —
  cheap, synchronous-feeling, no serialization. Used to decouple modules that
  live in the same deployment (e.g. the webhook doesn't call the orchestrator
  directly; it publishes `whatsapp.message_received` and the orchestrator
  subscribes).
- **Redis pub/sub** (best-effort) fans the same event out to other processes
  (a future dedicated worker, the AI Console, a metrics sidecar). It degrades
  silently if Redis is unavailable — the in-process path never depends on it.

This does not replace the durable job queue (`jobs/`): the bus is for
notifying interested parties about something that already happened
(fire-and-forget, no retry, no persistence guarantee). Anything that must
survive a crash or be retried belongs in a job, not an event handler.
"""

import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from redis import asyncio as aioredis

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

EventHandler = Callable[["Event"], Awaitable[None]]


@dataclass
class Event:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_json(self) -> str:
        return json.dumps(
            {
                "name": self.name,
                "payload": self.payload,
                "occurred_at": self.occurred_at.isoformat(),
            },
            default=str,
        )


class EventBus:
    """Async pub/sub. Subscribe with a name or a `"prefix.*"` wildcard."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._wildcard_handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._redis: aioredis.Redis | None = None
        self._redis_available = True

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Register a handler for an exact event name or a `"domain.*"` wildcard."""
        if event_name.endswith(".*"):
            self._wildcard_handlers[event_name[:-2]].append(handler)
        else:
            self._handlers[event_name].append(handler)

    def unsubscribe_all(self) -> None:
        """Test-only: reset all in-process subscriptions."""
        self._handlers.clear()
        self._wildcard_handlers.clear()

    async def publish(
        self, event_name: str, payload: dict[str, Any] | None = None
    ) -> Event:
        event = Event(name=event_name, payload=payload or {})

        for handler in self._matching_handlers(event_name):
            try:
                await handler(event)
            except Exception:  # noqa: BLE001 - one bad subscriber must not break others
                logger.exception("Event handler failed for %s", event_name)

        await self._publish_to_redis(event)
        return event

    def _matching_handlers(self, event_name: str) -> list[EventHandler]:
        handlers = list(self._handlers.get(event_name, []))
        domain = event_name.split(".", 1)[0]
        handlers.extend(self._wildcard_handlers.get(domain, []))
        return handlers

    async def _publish_to_redis(self, event: Event) -> None:
        if not self._redis_available:
            return
        try:
            if self._redis is None:
                self._redis = aioredis.from_url(
                    self._settings.redis_url, decode_responses=True
                )
            await self._redis.publish(self._settings.events_channel, event.to_json())
        except Exception:  # noqa: BLE001 - the bus must survive Redis being down
            logger.warning("Redis unavailable; events stay in-process only")
            self._redis_available = False


event_bus = EventBus()
