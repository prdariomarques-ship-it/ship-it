"""Yahoo Finance chart endpoint (unofficial, no key). Indices, stocks, ETFs, futures, crypto."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote

from ..domain import Instrument, ProviderError, Quote
from .http import JsonFetcher, fetch_json

SYMBOL = re.compile(r"^[A-Za-z0-9.^=\-]{1,20}$")


def _num(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v else None


class YahooProvider:
    def __init__(self, fetch: JsonFetcher = fetch_json) -> None:
        self._fetch = fetch

    def fetch(self, instrument: Instrument) -> Quote:
        sym = instrument.symbol
        if not SYMBOL.match(sym):
            raise ProviderError("invalid symbol")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(sym, safe='')}?range=5d&interval=1d"
        body = self._fetch(url)
        try:
            result = body["chart"]["result"][0]  # type: ignore[index]
            meta = result["meta"]
            stamps = result.get("timestamp") or []
            closes = (result["indicators"]["quote"][0].get("close")) or []
        except (KeyError, IndexError, TypeError) as exc:
            err = None
            try:
                err = body["chart"]["error"]["description"]  # type: ignore[index]
            except (KeyError, TypeError):
                pass
            raise ProviderError(str(err) if err else "unexpected response shape") from exc
        price = _num(meta.get("regularMarketPrice"))
        when = _num(meta.get("regularMarketTime"))
        if price is None or when is None:
            raise ProviderError("source returned no price")
        # Previous close = the close of the session BEFORE the latest one in the series. The latest point may be the
        # live session, so it is excluded by position, never by assuming 'chartPreviousClose' (which is the close
        # before the whole 5d window and would give a 5-day change).
        series = [c for _t, c in zip(stamps, closes, strict=False) if _num(c) is not None]
        change = None
        if len(series) >= 2 and series[-2]:
            change = (price / series[-2] - 1.0) * 100.0
        return Quote(instrument=instrument, value=price, as_of=datetime.fromtimestamp(when, tz=timezone.utc), change_pct=change)
