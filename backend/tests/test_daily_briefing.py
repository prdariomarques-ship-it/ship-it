"""Daily briefing: yield curve classification, basis-point math, message
formatting, and the self-rescheduling job (port of FlowCore's "Mercado"
feed) on the isolated financial worker."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from investments.daily_briefing import (
    BriefingSnapshot,
    Quote,
    _classify_shape,
    _classify_state,
    format_briefing_message,
)
from investments.jobs import DAILY_BRIEFING_JOB_NAME, TELEGRAM_SEND_JOB_NAME
from investments.models import FinancialJobStatus
from investments.repository import FinancialJobRepository
from investments.worker import FinancialWorker
from investments.yahoo_finance import latest_and_delta_bps


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def worker(session_factory, monkeypatch):
    monkeypatch.setattr("investments.worker.async_session_factory", session_factory)
    return FinancialWorker()


@pytest.fixture(autouse=True)
def _always_pregao(monkeypatch):
    monkeypatch.setattr("investments.jobs.is_pregao_now", lambda: True)


@pytest.fixture(autouse=True)
def _monitors_enabled(monkeypatch):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "market_monitors_enabled", True)


def _quote(source, category, symbol, unit, value, previous_close, delta):
    return Quote(source, category, symbol, unit, value, previous_close, delta, timestamp=1_700_000_000)


# ── basis points — the bug the review caught ─────────────────────────────────


def test_latest_and_delta_bps_is_absolute_not_relative():
    # 4.00% -> 4.10% is +10 bps. The old (buggy) relative-% calculation
    # would have reported +250 bps for this exact move.
    value, delta_bps = latest_and_delta_bps([4.00, 4.10])
    assert value == 4.10
    assert delta_bps == 10.0


def test_latest_and_delta_bps_negative_move():
    value, delta_bps = latest_and_delta_bps([5.25, 5.00])
    assert delta_bps == -25.0


# ── curve classification ─────────────────────────────────────────────────────


def test_classify_state_inverted():
    assert _classify_state(-5.0, None) == "inverted"


def test_classify_state_insufficient_data():
    assert _classify_state(None, None) == "insufficient_data"


def test_classify_state_steepening():
    assert _classify_state(120.0, 100.0) == "steepening"


def test_classify_shape_needs_two_prior_points():
    assert _classify_shape({"treasury": 4.0, "tbill_13wk": 3.5}, {"treasury": 4.0}) == (None, None)


def test_classify_shape_bear_steepening():
    points = {"treasury": 4.20, "tbill_13wk": 3.50, "treasury_30y": 4.50}
    prev = {"treasury": 4.00, "tbill_13wk": 3.55, "treasury_30y": 4.25}
    shape, interpretation = _classify_shape(points, prev)
    assert shape == "bear_steepening"
    assert interpretation is not None


# ── format_briefing_message — never says "10Y-2Y" ────────────────────────────


def test_format_briefing_message_includes_sections():
    snapshot = BriefingSnapshot(
        quotes={
            "dollar": _quote("dollar", "fx", "USDBRL=X", "price", 5.40, 5.35, 0.93),
            "dxy": _quote("dxy", "fx", "DX-Y.NYB", "price", 100.0, 99.0, 1.01),
            "sp500": _quote("sp500", "equities", "^GSPC", "price", 5000.0, 4900.0, 2.04),
        },
        curve=None,
    )
    message = format_briefing_message(snapshot)
    assert "RADAR DE MERCADO" in message
    assert "DÓLAR" in message
    assert "EQUITIES" in message.upper()


def test_format_briefing_message_never_claims_a_real_2y_treasury():
    from investments.daily_briefing import YieldCurveSummary

    snapshot = BriefingSnapshot(
        quotes={}, curve=YieldCurveSummary(
            points={"tbill_13wk": 4.5, "treasury": 4.2}, slope_10y_shortend_bps=-30.0,
            state="inverted", shape=None, interpretation=None,
        )
    )
    message = format_briefing_message(snapshot)
    assert "10Y-2Y" not in message
    assert "T-bill 13 sem." in message


# ── send_daily_briefing_job ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_daily_briefing_job_enqueues_telegram_message(session_factory, worker, monkeypatch):
    fake_snapshot = BriefingSnapshot(
        quotes={"dollar": _quote("dollar", "fx", "USDBRL=X", "price", 5.40, 5.35, 0.93)}, curve=None
    )

    async def _fake_fetch():
        return fake_snapshot

    monkeypatch.setattr("investments.jobs.fetch_briefing_snapshot", _fake_fetch)

    async with session_factory() as session:
        await FinancialJobRepository(session).create(name=DAILY_BRIEFING_JOB_NAME, payload={})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        sent = await FinancialJobRepository(session).find_one(name=TELEGRAM_SEND_JOB_NAME)
        assert sent is not None
        assert sent.payload["feed"] == "mercado"

        rescheduled = await FinancialJobRepository(session).find_one(
            name=DAILY_BRIEFING_JOB_NAME, status=FinancialJobStatus.QUEUED
        )
        assert rescheduled is not None


@pytest.mark.asyncio
async def test_daily_briefing_job_skips_when_no_tickers_resolved(session_factory, worker, monkeypatch):
    async def _fake_fetch():
        return BriefingSnapshot(quotes={}, curve=None)

    monkeypatch.setattr("investments.jobs.fetch_briefing_snapshot", _fake_fetch)

    async with session_factory() as session:
        await FinancialJobRepository(session).create(name=DAILY_BRIEFING_JOB_NAME, payload={})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        sent = await FinancialJobRepository(session).find_one(name=TELEGRAM_SEND_JOB_NAME)
        assert sent is None
