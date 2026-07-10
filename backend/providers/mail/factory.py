"""Factory for mail providers (Factory + Strategy patterns) — same shape as
`providers/llm/factory.py` and `providers/whatsapp/factory.py`. Swap
providers by changing MAIL_PROVIDER; the rest of the application only
depends on the MailProvider interface.
"""
from functools import lru_cache

from providers.mail.base import MailProvider
from providers.mail.gmail.provider import GmailProvider
from utils.config import get_settings

_PROVIDERS: dict[str, type[MailProvider]] = {
    "gmail": GmailProvider,
}


class UnknownMailProviderError(ValueError):
    pass


@lru_cache
def get_mail_provider() -> MailProvider:
    name = get_settings().mail_provider
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise UnknownMailProviderError(
            f"Unknown mail provider {name!r}. Available: {sorted(_PROVIDERS)}"
        ) from None
