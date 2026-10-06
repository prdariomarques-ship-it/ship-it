"""Shared Yahoo Finance fetch for every market monitor in this package.

No invented prices: a fetch/parse failure raises MarketDataError and the
caller must treat that as "no data", never as a real quote.
"""
import httpx

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
# Yahoo's chart endpoint 403s requests with no User-Agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DarioOS-MarketMonitor/1.0)"}


class MarketDataError(RuntimeError):
    pass


async def fetch_daily_closes(ticker: str, range_: str = "2mo") -> list[float]:
    """Real daily closes for `ticker`, oldest first, via Yahoo Finance's public chart API."""
    url = YAHOO_CHART_URL.format(ticker=ticker)
    params = {"range": range_, "interval": "1d"}
    try:
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise MarketDataError(f"Yahoo Finance request failed for {ticker}: {exc}") from exc

    try:
        result = data["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError) as exc:
        raise MarketDataError(f"Unexpected Yahoo Finance response shape for {ticker}") from exc

    closes = [c for c in closes if c is not None]
    if not closes:
        raise MarketDataError(f"Yahoo Finance returned no usable closes for {ticker}")
    return closes


def latest_and_delta_pct(closes: list[float]) -> tuple[float, float | None]:
    """Latest close and its 1-day % change (None if there's no prior close to compare)."""
    latest = closes[-1]
    if len(closes) < 2:
        return latest, None
    previous = closes[-2]
    delta_pct = (latest - previous) / previous * 100 if previous else None
    return latest, delta_pct
