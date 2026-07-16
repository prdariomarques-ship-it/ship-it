"""Factory for contacts providers (Factory + Strategy patterns) — same shape
as `providers/mail/factory.py` and `providers/calendar/factory.py`.
"""

from functools import lru_cache

from providers.contacts.base import ContactsProvider
from providers.contacts.google.provider import GoogleContactsProvider
from utils.config import get_settings

_PROVIDERS: dict[str, type[ContactsProvider]] = {
    "google": GoogleContactsProvider,
}


class UnknownContactsProviderError(ValueError):
    pass


@lru_cache
def get_contacts_provider() -> ContactsProvider:
    name = get_settings().contacts_provider
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise UnknownContactsProviderError(
            f"Unknown contacts provider {name!r}. Available: {sorted(_PROVIDERS)}"
        ) from None
