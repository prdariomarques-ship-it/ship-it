"""Domain model. No I/O, no framework: everything here is plain data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Kind = Literal["yahoo", "fx", "sgs", "focus", "gold_brl"]


class ProviderError(Exception):
    """A quote could not be obtained. The message is safe to show to the user (no URLs with secrets)."""


@dataclass(frozen=True)
class Instrument:
    kind: Kind
    symbol: str          # yahoo ticker | "USD-BRL" (fx) | SGS code | "Indicador:Ano" (focus) | "" (gold_brl)
    name: str
    unit: str = ""       # "pts", "R$", "US$", "% a.a." ...
    decimals: int = 2


@dataclass(frozen=True)
class Quote:
    instrument: Instrument
    value: float
    as_of: datetime                  # timezone-aware UTC; when the SOURCE observed this value
    change_pct: float | None = None  # vs previous close; None = the source did not give one (never 0)


@dataclass(frozen=True)
class Result:
    """Outcome for one instrument: exactly one of quote / error is set."""
    instrument: Instrument
    quote: Quote | None = None
    error: str | None = None


@dataclass(frozen=True)
class Section:
    id: str              # also the chat command (/indices)
    title: str
    instruments: tuple[Instrument, ...]
    note: str = ""       # shown under the title (e.g. a declared coverage gap)


@dataclass(frozen=True)
class MoversSpec:
    title: str
    universe: tuple[Instrument, ...]   # yahoo instruments, evaluated together
    top_n: int = 5


@dataclass(frozen=True)
class Filing:
    key: str             # stable id (protocol / link) used for de-duplication
    company: str
    category: str
    subject: str
    delivered_at: datetime   # UTC
    link: str = ""


@dataclass(frozen=True)
class FilingsSpec:
    categories: tuple[str, ...] = ("Fato Relevante",)
    companies: tuple[str, ...] = ()    # case-insensitive substrings; empty = every company
    window_hours: int = 24
    max_items: int = 8


@dataclass(frozen=True)
class AlertRule:
    symbol: str                 # must match an instrument symbol of the profile
    min_abs_change_pct: float
    label: str = ""


@dataclass(frozen=True)
class Profile:
    id: str                          # "national" | "global"
    title: str
    token_env: str
    chat_env: str
    schedule: tuple[str, ...]        # "HH:MM" local times
    weekdays_only: bool
    sections: tuple[Section, ...]
    catchup_minutes: int = 30
    movers: MoversSpec | None = None
    filings: FilingsSpec | None = None
    alerts: tuple[AlertRule, ...] = ()
    alert_interval_minutes: int = 15
    alert_window: tuple[str, str] = ("10:00", "18:00")
