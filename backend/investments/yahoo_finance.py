"""Shared Yahoo Finance fetch for every market monitor in this package.

No invented prices: a fetch/parse failure raises MarketDataError and the
caller must treat that as "no data", never as a real quote. Every series
carries its real per-point timestamp from Yahoo's own response, so a
caller can tell a fresh quote from a stale one instead of presenting
whatever Yahoo last cached as if it were current.
"""
import asyncio
import math
from dataclasses import dataclass
from datetime import datetime, timezone

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
# Daily-bar data older than this is treated as stale, not current — a
# backstop that covers any long weekend/holiday regardless of exchange
# calendar. is_pregao_now() (investments/b3_calendar.py) now also gates on
# the actual computed B3 holiday calendar, but only for B3 — this module
# still has no calendar for the US/European/Asian exchanges the daily
# briefing quotes (see that module's docstring). This threshold only decides
# whether to use the data AT ALL (StaleDataError above it); it does not by
# itself mean the data should be presented as if it were today's — that's
# FRESH_ENOUGH_HOURS below, a much tighter bar, because tolerating a few
# days of old data as "not broken" is a different claim from "this is a
# current quote", and callers must not conflate the two.
STALE_AFTER_SECONDS = 4 * 24 * 3600

# Below this, a quote is presented as current with no caveat. Above it
# (but still under STALE_AFTER_SECONDS), the data is used but every
# message built from it must say explicitly how old it is — never
# implied to be "now" just because it wasn't old enough to reject outright.
# ~20h covers a same-day quote fetched slightly before/after a given
# market's own session without silently spanning an entire extra day.
FRESH_ENOUGH_HOURS = 20.0


def age_disclosure(age_hours: float) -> str:
    """"" when fresh enough to show with no caveat; otherwise an explicit,
    user-facing line stating the data's real age — this exists specifically
    so "we didn't reject the data as broken" is never read as "this is
    current". Purely clock-based: the B3 holiday calendar is applied
    upstream, in is_pregao_now() deciding whether to run the check at all
    (see b3_calendar.py); this function itself still knows nothing about
    any calendar, B3's or otherwise."""
    if age_hours <= FRESH_ENOUGH_HOURS:
        return ""
    return f"⚠️ dado de {age_hours:.0f}h atrás — pregão de hoje não confirmado"


class MarketDataError(RuntimeError):
    pass


class StaleDataError(MarketDataError):
    """The freshest point Yahoo returned is older than STALE_AFTER_SECONDS —
    refuse to present it as a current quote."""


@dataclass
class PriceSeries:
    closes: list[float]  # oldest first
    timestamps: list[int]  # unix seconds, aligned 1:1 with closes

    @property
    def latest_close(self) -> float:
        return self.closes[-1]

    @property
    def latest_timestamp(self) -> int:
        return self.timestamps[-1]

    def age_seconds(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        return now.timestamp() - self.latest_timestamp


async def fetch_price_series(ticker: str, range_: str = "2mo") -> PriceSeries:
    """Real daily closes for `ticker`, oldest first, each with its real
    trading-day timestamp. Raises StaleDataError if the freshest point is
    older than STALE_AFTER_SECONDS — a caller must not quietly treat it as
    today's price."""
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
        raw_closes = result["indicators"]["quote"][0]["close"]
        raw_timestamps = result["timestamp"]
    except (KeyError, IndexError, TypeError) as exc:
        raise MarketDataError(f"Unexpected Yahoo Finance response shape for {ticker}") from exc

    if len(raw_closes) != len(raw_timestamps):
        raise MarketDataError(f"Mismatched closes/timestamps length for {ticker}")

    # Small allowance for clock skew between this process and Yahoo's
    # servers — anything further ahead than that is malformed/corrupt
    # data, not a real future trading timestamp, and must be dropped
    # rather than silently accepted (it would otherwise read as
    # impossibly "fresh", defeating the whole point of age_disclosure).
    max_valid_timestamp = datetime.now(timezone.utc).timestamp() + 300

    closes: list[float] = []
    timestamps: list[int] = []
    for close, ts in zip(raw_closes, raw_timestamps):
        if close is None or ts is None:
            continue
        if not math.isfinite(close):
            logger.warning("Dropping non-finite close for %s at ts=%s: %r", ticker, ts, close)
            continue
        if ts > max_valid_timestamp:
            logger.warning("Dropping future-dated point for %s: ts=%s is after now", ticker, ts)
            continue
        closes.append(float(close))
        timestamps.append(int(ts))

    if not closes:
        raise MarketDataError(f"Yahoo Finance returned no usable closes for {ticker}")

    series = PriceSeries(closes=closes, timestamps=timestamps)
    age = series.age_seconds()
    if age > STALE_AFTER_SECONDS:
        raise StaleDataError(
            f"{ticker}: freshest close is {age / 3600:.1f}h old (limit {STALE_AFTER_SECONDS / 3600:.0f}h)"
        )
    return series


async def fetch_daily_closes(ticker: str, range_: str = "2mo") -> list[float]:
    """Backward-compatible helper for callers that only need the closes."""
    return (await fetch_price_series(ticker, range_=range_)).closes


async def fetch_many_price_series(tickers: list[str], range_: str = "5d") -> dict[str, PriceSeries]:
    """Best-effort batch fetch: tickers that fail (including stale data) are
    logged and left out of the result rather than failing the whole batch —
    callers report what's available, honestly, same as every other monitor
    in this package."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _fetch_one(ticker: str) -> tuple[str, PriceSeries | None]:
        async with semaphore:
            try:
                return ticker, await fetch_price_series(ticker, range_=range_)
            except MarketDataError as exc:
                logger.warning("Skipping %s in batch fetch: %s", ticker, exc)
                return ticker, None

    results = await asyncio.gather(*(_fetch_one(t) for t in tickers))
    return {ticker: series for ticker, series in results if series is not None}


async def fetch_many_daily_closes(tickers: list[str], range_: str = "5d") -> dict[str, list[float]]:
    """Backward-compatible helper for callers that only need the closes."""
    series_by_ticker = await fetch_many_price_series(tickers, range_=range_)
    return {ticker: series.closes for ticker, series in series_by_ticker.items()}


def latest_and_delta_pct(closes: list[float]) -> tuple[float, float | None]:
    """Latest close and its 1-day % change (None if there's no prior close to
    compare) — relative change, correct for prices. For a yield/rate series
    (percentage-point units), use latest_and_delta_bps instead: a relative
    % change of a yield is not the same thing as its move in basis points."""
    latest = closes[-1]
    if len(closes) < 2:
        return latest, None
    previous = closes[-2]
    delta_pct = (latest - previous) / previous * 100 if previous else None
    return latest, delta_pct


def latest_and_delta_bps(closes: list[float]) -> tuple[float, float | None]:
    """Latest yield (percentage points, e.g. 4.32) and its 1-day change in
    basis points — an ABSOLUTE point difference × 100, e.g. 4.00% -> 4.10%
    is +10 bps, never a relative-percent calculation (which would read
    that same move as +250 bps)."""
    latest = closes[-1]
    if len(closes) < 2:
        return latest, None
    previous = closes[-2]
    return latest, round((latest - previous) * 100, 1)
