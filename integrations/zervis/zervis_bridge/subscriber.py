"""Assinante do canal Redis de eventos do Dario OS."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from redis import asyncio as aioredis

from .buffer import EventBuffer
from .sanitize import sanitize_event

logger = logging.getLogger(__name__)


class EventSubscriber:
    """Lê `channel`, sanitiza e empilha no buffer; reconecta com backoff.

    O bus publica fire-and-forget, sem persistência: o que acontece com a ponte
    fora do ar não é recuperável, e o buffer sinaliza lacunas (`gap`) para o
    consumidor. `connected` alimenta a tool de status.
    """

    def __init__(
        self,
        redis_url: str,
        channel: str,
        buffer: EventBuffer,
        *,
        backoff_max: float = 30.0,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._channel = channel
        self._buffer = buffer
        self._backoff_max = backoff_max
        self._client_factory = client_factory or (
            lambda url: aioredis.from_url(url, decode_responses=True)
        )
        self.connected = False
        self.dropped = 0

    def handle(self, data: Any) -> None:
        try:
            raw = json.loads(data)
        except (TypeError, ValueError):
            self.dropped += 1
            return
        event = sanitize_event(raw)
        if event is None:
            self.dropped += 1
            return
        self._buffer.append(event)

    async def run(self) -> None:
        delay = 1.0
        while True:
            client = None
            try:
                client = self._client_factory(self._redis_url)
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                await pubsub.subscribe(self._channel)
                self.connected = True
                delay = 1.0
                logger.info("Assinando %s", self._channel)
                async for message in pubsub.listen():
                    self.handle(message.get("data"))
                raise ConnectionError("canal encerrado pelo servidor")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - o assinante precisa sobreviver
                logger.warning(
                    "Redis indisponível (%s); nova tentativa em %.0fs",
                    type(exc).__name__,
                    delay,
                )
            finally:
                self.connected = False
                if client is not None:
                    try:
                        await client.aclose()
                    except Exception:  # noqa: BLE001
                        pass
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._backoff_max)
