"""Economic Calendar Provider abstraction — Strategy pattern.

Business services depend ONLY on this interface.  Specific vendors
(RapidAPI, Mock, future providers) implement the same contract.

Design rules:
- No business logic lives in providers — translation and transport only.
- No database access, no LLM calls, no caching — those belong to the
  service layer (services/economic_calendar.py).
- The provider converts vendor-specific shapes into the neutral types
  defined below.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class Volatility(str, Enum):
    """Pre-classified impact level for an economic event."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EconomicEvent(BaseModel):
    """A single economic calendar event, normalized across providers."""
    id: str
    name: str
    country_code: str
    country_name: str = ""
    currency: str = ""
    date_utc: datetime
    volatility: Volatility
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None
    unit: str | None = None
    category: str | None = None
    impact: str | None = None
    url: str | None = None


class EconomicEventList(BaseModel):
    """Container for a list of economic events with metadata."""
    events: list[EconomicEvent]
    total: int
    from_date: str | None = None
    to_date: str | None = None
    country_filter: str | None = None
    volatility_filter: str | None = None


class EconomicCalendarProviderError(RuntimeError):
    """Raised when the underlying provider fails (HTTP error, parse error,
    rate limit, etc.).  The service layer catches this and returns a
    graceful fallback response."""
    pass


class EconomicCalendarProvider(ABC):
    """Contract that every economic calendar provider must fulfil."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider identifier (e.g. 'rapidapi', 'mock')."""
        ...

    @abstractmethod
    async def list_events(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        country_code: str | None = None,
        volatility: Volatility | str | None = None,
        limit: int = 100,
    ) -> EconomicEventList:
        """Fetch upcoming (or recent) economic events.

        Parameters
        ----------
        start_date :
            Lower bound for event date (UTC).  Defaults to today.
        end_date :
            Upper bound for event date (UTC).  Defaults to 7 days ahead.
        country_code :
            ISO country code filter (e.g. 'US', 'BR', 'EU').  None = all.
        volatility :
            Filter by minimum impact: NONE/LOW/MEDIUM/HIGH.
            None = all.
        limit :
            Maximum number of events to return.

        Returns
        -------
        EconomicEventList
            Normalized events from this provider.

        Raises
        ------
        EconomicCalendarProviderError
            If the upstream call fails.
        """
        ...

    @abstractmethod
    async def list_countries(self) -> list[dict[str, str]]:
        """Return available countries with their ISO codes.

        Returns
        -------
        list[dict]
            Each item has at least ``code`` and ``name`` keys.
        """
        ...
