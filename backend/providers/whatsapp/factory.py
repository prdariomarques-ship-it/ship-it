"""Factory for WhatsApp providers (Factory + Strategy patterns).

Swap gateways by changing WHATSAPP_PROVIDER in the environment — the rest of
the application only depends on the WhatsAppProvider interface.
"""

from functools import lru_cache

from providers.whatsapp.baileys.provider import BaileysProvider
from providers.whatsapp.base import WhatsAppProvider
from providers.whatsapp.evolution.provider import EvolutionProvider
from providers.whatsapp.official.provider import OfficialProvider
from providers.whatsapp.openwa.provider import OpenWAProvider
from utils.config import get_settings

_PROVIDERS: dict[str, type[WhatsAppProvider]] = {
    "openwa": OpenWAProvider,
    "baileys": BaileysProvider,
    "evolution": EvolutionProvider,
    "official": OfficialProvider,
}


class UnknownProviderError(ValueError):
    pass


@lru_cache
def get_whatsapp_provider() -> WhatsAppProvider:
    name = get_settings().whatsapp_provider
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise UnknownProviderError(
            f"Unknown WhatsApp provider {name!r}. Available: {sorted(_PROVIDERS)}"
        ) from None
