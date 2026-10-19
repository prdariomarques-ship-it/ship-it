from __future__ import annotations

from ..domain import Instrument, ProviderError, Quote
from ..ports import QuoteProvider
from .awesomeapi import AwesomeApiFx
from .bcb import BcbSgs
from .focus import BcbFocus
from .gold import GoldBrlPerGram
from .yahoo import YahooProvider


class RoutingProvider:
    """Dispatches by Instrument.kind (Registry pattern): a new source = one more registered provider."""

    def __init__(self, providers: dict[str, QuoteProvider] | None = None) -> None:
        if providers is None:
            yahoo, fx = YahooProvider(), AwesomeApiFx()
            providers = {"yahoo": yahoo, "fx": fx, "sgs": BcbSgs(), "focus": BcbFocus(),
                         "gold_brl": GoldBrlPerGram(yahoo, fx)}
        self._providers = providers

    def fetch(self, instrument: Instrument) -> Quote:
        provider = self._providers.get(instrument.kind)
        if provider is None:
            raise ProviderError(f"no provider registered for {instrument.kind!r}")
        return provider.fetch(instrument)


__all__ = ["RoutingProvider", "YahooProvider", "AwesomeApiFx", "BcbSgs", "BcbFocus", "GoldBrlPerGram"]
