"""Factory for economic calendar providers — Factory + Strategy patterns.

Mirrors ``providers/calendar/factory.py``: swap providers by changing
``ECONOMIC_CALENDAR_PROVIDER`` in settings.  The rest of the application
only depends on the ``EconomicCalendarProvider`` interface.

Auto-fallback: if ECONOMIC_CALENDAR_API_KEY is not set, the factory
returns the Mock provider automatically so the app never crashes — it
just shows synthetic data until a real key is configured.
"""
from functools import lru_cache
from providers.economic_calendar.base import EconomicCalendarProvider
from providers.economic_calendar.mock import MockEconomicCalendarProvider
from providers.economic_calendar.rapidapi import RapidAPIEconomicCalendarProvider
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

_PROVIDERS: dict[str, type[EconomicCalendarProvider]] = {
    "rapidapi": RapidAPIEconomicCalendarProvider,
    "mock": MockEconomicCalendarProvider,
}


class UnknownEconomicCalendarProviderError(ValueError):
    pass


@lru_cache
def get_economic_calendar_provider() -> EconomicCalendarProvider:
    """Return the configured economic calendar provider.

    Logic:
    1. Read ``ECONOMIC_CALENDAR_PROVIDER`` from settings (default: ``rapidapi``).
    2. If the requested provider is ``rapidapi`` but ``ECONOMIC_CALENDAR_API_KEY``
       is empty, automatically fall back to ``mock`` and log a warning.
    3. Instantiate and return the provider.
    """
    settings = get_settings()
    name = settings.economic_calendar_provider

    # Auto-fallback: rapidapi without API key → mock
    if name == "rapidapi" and not settings.economic_calendar_api_key:
        logger.warning(
            "ECONOMIC_CALENDAR_API_KEY is not set. "
            "Falling back to MockEconomicCalendarProvider. "
            "Set the env var to enable real data."
        )
        return MockEconomicCalendarProvider()

    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise UnknownEconomicCalendarProviderError(
            f"Unknown economic calendar provider {name!r}. "
            f"Available: {sorted(_PROVIDERS)}"
        ) from None
