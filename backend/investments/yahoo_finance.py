"""Shared Yahoo Finance fetch for every market monitor in this package.

No invented prices: a fetch/parse failure raises MarketDataError and the
caller must treat that as "no data", never as a real quote.
"""
import asyncio

import httpx

from utils.logging import get_logger

logger = get_logger(__name__)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
# Yahoo's chart endpoint 403s requests with no User-Agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DarioOS-MarketMonitor/1.0)"}
# A full briefing fans out to ~25 tickers; the original FlowCore observers
# found 16 concurrent Yahoo connections oversubscribes a constrained link
# and times out *more*, not less — 6 workers was the tuned-down fix there,
# mirrored here even though a VPS isn't as constrained as the mobile link
# that prompted it.
_MAX_CONCURRENCY = 6


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


async def fetch_many_daily_closes(tickers: list[str], range_: str = "5d") -> dict[str, list[float]]:
    """Best-effort batch fetch: tickers that fail are logged and left out of
    the result rather than failing the whole batch — callers report what's
    available, honestly, same as every other monitor in this package."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _fetch_one(ticker: str) -> tuple[str, list[float] | None]:
        async with semaphore:
            try:
                return ticker, await fetch_daily_closes(ticker, range_=range_)
            except MarketDataError as exc:
                logger.warning("Skipping %s in batch fetch: %s", ticker, exc)
                return ticker, None

    results = await asyncio.gather(*(_fetch_one(t) for t in tickers))
    return {ticker: closes for ticker, closes in results if closes is not None}


def latest_and_delta_pct(closes: list[float]) -> tuple[float, float | None]:
    """Latest close and its 1-day % change (None if there's no prior close to compare)."""
    latest = closes[-1]
    if len(closes) < 2:
        return latest, None
    previous = closes[-2]
    delta_pct = (latest - previous) / previous * 100 if previous else None
    return latest, delta_pct
