"""SPCX34.SA Bollinger-band (banda superior) check against real Yahoo Finance data.

No invented prices or bands: a fetch/parse failure raises MarketDataError and
the caller must treat that as "no data", never as "price below band".
"""
import statistics
from dataclasses import dataclass

from investments.yahoo_finance import MarketDataError, fetch_price_series
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SPCX34Check:
    ticker: str
    price: float
    upper_band: float
    triggered: bool
    quote_timestamp: int  # unix seconds — the price's own trading-day timestamp from Yahoo
    quote_age_hours: float  # declared explicitly in the alert text — see jobs.py


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
    series = await fetch_price_series(ticker)
    upper_band = bollinger_upper_band(series.closes, window, std_mult)
    price = series.latest_close
    return SPCX34Check(
        ticker=ticker, price=price, upper_band=upper_band, triggered=price > upper_band,
        quote_timestamp=series.latest_timestamp, quote_age_hours=series.age_seconds() / 3600,
    )
