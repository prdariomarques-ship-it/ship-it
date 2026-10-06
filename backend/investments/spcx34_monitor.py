"""SPCX34.SA Bollinger-band (banda superior) check against real Yahoo Finance data.

No invented prices or bands: a fetch/parse failure raises MarketDataError and
the caller must treat that as "no data", never as "price below band".
"""
import statistics
from dataclasses import dataclass

import httpx

from utils.logging import get_logger

logger = get_logger(__name__)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
# Yahoo's chart endpoint 403s requests with no User-Agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DarioOS-MarketMonitor/1.0)"}


class MarketDataError(RuntimeError):
    pass


@dataclass
class SPCX34Check:
    ticker: str
    price: float
    upper_band: float
    triggered: bool


async def fetch_daily_closes(ticker: str) -> list[float]:
    """Real daily closes for `ticker`, oldest first, via Yahoo Finance's public chart API."""
    url = YAHOO_CHART_URL.format(ticker=ticker)
    params = {"range": "2mo", "interval": "1d"}
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


def bollinger_upper_band(closes: list[float], window: int, std_mult: float) -> float:
    if len(closes) < window:
        raise MarketDataError(
            f"Need at least {window} closes for the Bollinger window, got {len(closes)}"
        )
    sample = closes[-window:]
    mean = statistics.fmean(sample)
    stdev = statistics.stdev(sample)
    return mean + std_mult * stdev


async def check_spcx34(ticker: str, window: int, std_mult: float) -> SPCX34Check:
    closes = await fetch_daily_closes(ticker)
    upper_band = bollinger_upper_band(closes, window, std_mult)
    price = closes[-1]
    return SPCX34Check(ticker=ticker, price=price, upper_band=upper_band, triggered=price > upper_band)
