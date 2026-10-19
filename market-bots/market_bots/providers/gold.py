"""Gold in R$ per gram, derived from COMEX gold (US$/oz) and USD/BRL. Both legs must be available."""
from __future__ import annotations

from dataclasses import replace

from ..domain import Instrument, ProviderError, Quote
from ..ports import QuoteProvider

TROY_OUNCE_G = 31.1034768
GOLD = Instrument(kind="yahoo", symbol="GC=F", name="Ouro", unit="US$/oz")
USDBRL = Instrument(kind="fx", symbol="USD-BRL", name="USD/BRL", unit="R$")


class GoldBrlPerGram:
    def __init__(self, yahoo: QuoteProvider, fx: QuoteProvider) -> None:
        self._yahoo = yahoo
        self._fx = fx

    def fetch(self, instrument: Instrument) -> Quote:
        gold = self._yahoo.fetch(GOLD)      # a failing leg raises: no half-derived number is ever shown
        usd = self._fx.fetch(USDBRL)     # same source as the "Dólar" line: the two never disagree
        value = gold.value * usd.value / TROY_OUNCE_G
        change = None
        if gold.change_pct is not None and usd.change_pct is not None:
            change = ((1 + gold.change_pct / 100) * (1 + usd.change_pct / 100) - 1) * 100
        if value <= 0:
            raise ProviderError("invalid derived value")
        return replace(Quote(instrument=instrument, value=value, as_of=min(gold.as_of, usd.as_of), change_pct=change))
