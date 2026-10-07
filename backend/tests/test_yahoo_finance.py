"""yahoo_finance: basis-point-safe delta math, staleness, and the explicit
age-disclosure line every monitor message must carry when data isn't
fresh enough to present as current (the review's point: tolerating a few
days of old data as "not broken" is not the same claim as "this is now")."""
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from investments.yahoo_finance import (
    FRESH_ENOUGH_HOURS,
    MarketDataError,
    PriceSeries,
    STALE_AFTER_SECONDS,
    StaleDataError,
    age_disclosure,
    fetch_price_series,
)

_RealAsyncClient = httpx.AsyncClient  # captured before any monkeypatching


def _patch_client(monkeypatch, handler) -> None:
    def _make_client(**kwargs):
        kwargs.pop("timeout", None)
        kwargs.pop("headers", None)
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("investments.yahoo_finance.httpx.AsyncClient", _make_client)


def _chart_response(closes: list, timestamps: list) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "chart": {
                "result": [{"timestamp": timestamps, "indicators": {"quote": [{"close": closes}]}}],
                "error": None,
            }
        },
    )


def _chart_response_raw(closes_literal: str, timestamps: list) -> httpx.Response:
    """Builds the response body as raw text rather than via httpx's json=
    kwarg, which refuses to encode NaN/Infinity (allow_nan=False — correctly,
    since those aren't valid JSON). Real upstream APIs occasionally emit the
    non-standard NaN/Infinity literals anyway, and Python's own json.loads
    accepts them on decode by default — so this is what `response.json()`
    actually sees over the wire in that case, not something only our test
    harness could produce."""
    body = (
        '{"chart": {"result": [{"timestamp": %s, '
        '"indicators": {"quote": [{"close": [%s]}]}}], "error": null}}'
    ) % (timestamps, closes_literal)
    return httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "application/json"})


def test_age_disclosure_empty_when_fresh():
    assert age_disclosure(1.0) == ""
    assert age_disclosure(FRESH_ENOUGH_HOURS) == ""


def test_age_disclosure_warns_past_threshold():
    line = age_disclosure(FRESH_ENOUGH_HOURS + 0.1)
    assert line != ""
    assert "pregão de hoje não confirmado" in line


def test_age_disclosure_states_the_actual_age():
    line = age_disclosure(72.0)
    assert "72h" in line


def test_price_series_age_seconds():
    now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    series = PriceSeries(closes=[1.0, 2.0], timestamps=[int((now - timedelta(hours=5)).timestamp()), int(now.timestamp()) - 3600])
    assert series.age_seconds(now) == pytest.approx(3600, abs=1)


def test_stale_after_seconds_is_four_days():
    assert STALE_AFTER_SECONDS == 4 * 24 * 3600


# ── fetch_price_series: invalid data is dropped, not trusted ────────────────


@pytest.mark.asyncio
async def test_fetch_price_series_drops_future_timestamps(monkeypatch):
    now = int(time.time())
    future = now + 3600 * 24  # a day in the future — not clock skew, malformed
    handler = lambda request: _chart_response([10.0, 11.0, 999.0], [now - 7200, now - 3600, future])  # noqa: E731
    _patch_client(monkeypatch, handler)

    series = await fetch_price_series("TEST", range_="5d")
    assert series.closes == [10.0, 11.0]
    assert future not in series.timestamps


@pytest.mark.asyncio
async def test_fetch_price_series_drops_non_finite_closes(monkeypatch):
    now = int(time.time())
    handler = lambda request: _chart_response_raw(  # noqa: E731
        "10.0, NaN, Infinity, 11.0", [now - 7200, now - 5400, now - 3600, now - 1800]
    )
    _patch_client(monkeypatch, handler)

    series = await fetch_price_series("TEST", range_="5d")
    assert series.closes == [10.0, 11.0]


@pytest.mark.asyncio
async def test_fetch_price_series_raises_when_all_points_invalid(monkeypatch):
    now = int(time.time())
    handler = lambda request: _chart_response_raw("null, NaN", [now, now])  # noqa: E731
    _patch_client(monkeypatch, handler)

    with pytest.raises(MarketDataError):
        await fetch_price_series("TEST", range_="5d")


@pytest.mark.asyncio
async def test_fetch_price_series_raises_stale_data_error_past_four_days(monkeypatch):
    old = int(time.time()) - STALE_AFTER_SECONDS - 3600
    handler = lambda request: _chart_response([10.0], [old])  # noqa: E731
    _patch_client(monkeypatch, handler)

    with pytest.raises(StaleDataError):
        await fetch_price_series("TEST", range_="5d")


@pytest.mark.asyncio
async def test_fetch_price_series_partial_failure_is_a_clean_per_ticker_error(monkeypatch):
    """A malformed/error response for one ticker must raise cleanly (so
    fetch_many_price_series's per-ticker try/except can drop just that
    one) rather than crash in some unexpected way."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"chart": {"result": None, "error": {"description": "Not Found"}}})

    _patch_client(monkeypatch, handler)
    with pytest.raises(MarketDataError):
        await fetch_price_series("BADTICKER", range_="5d")
