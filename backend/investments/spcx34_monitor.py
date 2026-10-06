"""SPCX34.SA Bollinger-band (banda superior) check against real Yahoo Finance data.

No invented prices or bands: a fetch/parse failure raises MarketDataError and
the caller must treat that as "no data", never as "price below band".
"""
import statistics
from dataclasses import dataclass

from investments.yahoo_finance import MarketDataError, fetch_daily_closes
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SPCX34Check:
    ticker: str
    price: float
    upper_band: float
    triggered: bool


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
