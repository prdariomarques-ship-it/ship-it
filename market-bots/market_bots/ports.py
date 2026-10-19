"""Ports (interfaces) the application depends on. Adapters implement them; tests fake them."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .domain import Instrument, Quote


class QuoteProvider(Protocol):
    def fetch(self, instrument: Instrument) -> Quote:
        """Return a quote or raise ProviderError. Must never return a cached value as if it were fresh."""


class Notifier(Protocol):
    def send(self, chat_id: str, text: str) -> None:
        """Deliver text or raise. A normal return means the transport accepted the message."""


class StateStore(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime:
        """Timezone-aware 'now' in UTC."""
