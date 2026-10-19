"""AwesomeAPI FX (no key): symbol 'USD-BRL'."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from ..domain import Instrument, ProviderError, Quote
from .http import JsonFetcher, fetch_json

PAIR = re.compile(r"^[A-Z]{3}-[A-Z]{3}$")


class AwesomeApiFx:
    def __init__(self, fetch: JsonFetcher = fetch_json) -> None:
        self._fetch = fetch

    def fetch(self, instrument: Instrument) -> Quote:
        pair = instrument.symbol
        if not PAIR.match(pair):
            raise ProviderError("invalid currency pair")
        body = self._fetch(f"https://economia.awesomeapi.com.br/json/last/{pair}")
        try:
            row = body[pair.replace("-", "")]  # type: ignore[index]
            value = float(row["bid"])
            ts = int(row["timestamp"])
            pct = float(row["pctChange"]) if row.get("pctChange") not in (None, "") else None
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("unexpected response shape") from exc
        return Quote(instrument=instrument, value=value, as_of=datetime.fromtimestamp(ts, tz=timezone.utc), change_pct=pct)
