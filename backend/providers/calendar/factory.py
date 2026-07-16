"""Factory for calendar providers (Factory + Strategy patterns) — same shape
as `providers/mail/factory.py`. Swap providers by changing CALENDAR_PROVIDER;
the rest of the application only depends on the CalendarProvider interface.
"""

from functools import lru_cache

from providers.calendar.base import CalendarProvider
from providers.calendar.google.provider import GoogleCalendarProvider
from utils.config import get_settings

_PROVIDERS: dict[str, type[CalendarProvider]] = {
    "google": GoogleCalendarProvider,
}


class UnknownCalendarProviderError(ValueError):
    pass


@lru_cache
def get_calendar_provider() -> CalendarProvider:
    name = get_settings().calendar_provider
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise UnknownCalendarProviderError(
            f"Unknown calendar provider {name!r}. Available: {sorted(_PROVIDERS)}"
        ) from None
