from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from market_bots.domain import Filing, FilingsSpec, Instrument, ProviderError, Quote

TZ = ZoneInfo("America/Sao_Paulo")


def utc(y, mo, d, h=0, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def local(y, mo, d, h=0, mi=0) -> datetime:
    """A São Paulo wall-clock time expressed as aware UTC."""
    return datetime(y, mo, d, h, mi, tzinfo=TZ).astimezone(timezone.utc)


class FakeProvider:
    """Scripted quotes by symbol: (value, change_pct) | Exception. Counts calls."""

    def __init__(self, table: dict[str, object], as_of: datetime) -> None:
        self.table = table
        self.as_of = as_of
        self.calls: list[str] = []

    def fetch(self, instrument: Instrument) -> Quote:
        self.calls.append(instrument.symbol)
        spec = self.table.get(instrument.symbol)
        if spec is None:
            raise ProviderError("sem cotação")
        if isinstance(spec, Exception):
            raise spec
        value, change = spec
        return Quote(instrument=instrument, value=value, as_of=self.as_of, change_pct=change)


class FakeFilings:
    def __init__(self, items: list[Filing] | Exception) -> None:
        self.items = items

    def recent(self, spec: FilingsSpec, now: datetime) -> list[Filing]:
        if isinstance(self.items, Exception):
            raise self.items
        return list(self.items)


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail_next = 0

    def send(self, chat_id: str, text: str) -> None:
        from market_bots.telegram import DeliveryError

        if self.fail_next > 0:
            self.fail_next -= 1
            raise DeliveryError("boom")
        self.sent.append((chat_id, text))


class MemState:
    def __init__(self) -> None:
        self.d: dict[str, str] = {}

    def get(self, key: str):
        return self.d.get(key)

    def set(self, key: str, value: str) -> None:
        self.d[key] = value


@pytest.fixture
def state() -> MemState:
    return MemState()


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()
