"""Factory for Drive providers (Factory + Strategy patterns) — same shape
as `providers/mail/factory.py`, `providers/calendar/factory.py` and
`providers/contacts/factory.py`.
"""

from functools import lru_cache

from providers.drive.base import DriveProvider
from providers.drive.google.provider import GoogleDriveProvider
from utils.config import get_settings

_PROVIDERS: dict[str, type[DriveProvider]] = {
    "google": GoogleDriveProvider,
}


class UnknownDriveProviderError(ValueError):
    pass


@lru_cache
def get_drive_provider() -> DriveProvider:
    name = get_settings().drive_provider
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise UnknownDriveProviderError(
            f"Unknown drive provider {name!r}. Available: {sorted(_PROVIDERS)}"
        ) from None
