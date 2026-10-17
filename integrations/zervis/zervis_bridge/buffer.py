"""Buffer circular de eventos, com TTL e cursor monotônico."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import Any


class EventBuffer:
    """Guarda os últimos N eventos por até `ttl_seconds`.

    Cada evento recebe um `seq` crescente; o consumidor guarda o último que viu
    e pede `since(seq)`. Se o buffer já descartou eventos que ele não viu, a
    resposta diz `gap: True` em vez de fingir continuidade.
    """

    def __init__(
        self,
        max_events: int,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._items: deque[tuple[int, float, dict[str, Any]]] = deque(maxlen=max_events)
        self._ttl = ttl_seconds
        self._clock = clock
        self._seq = 0

    @property
    def latest_seq(self) -> int:
        return self._seq

    def append(self, event: dict[str, Any]) -> int:
        self._seq += 1
        self._items.append((self._seq, self._clock(), event))
        return self._seq

    def _expire(self) -> None:
        cutoff = self._clock() - self._ttl
        while self._items and self._items[0][1] < cutoff:
            self._items.popleft()

    def since(self, seq: int = 0, limit: int = 50) -> dict[str, Any]:
        self._expire()
        oldest = self._items[0][0] if self._items else self._seq + 1
        gap = seq + 1 < oldest and seq < self._seq
        events = [{"seq": s, **event} for s, _, event in self._items if s > seq][:limit]
        next_seq = events[-1]["seq"] if events else max(seq, self._seq if gap else seq)
        return {
            "events": events,
            "next_seq": next_seq,
            "latest_seq": self._seq,
            "gap": gap,
        }
