"""Daily briefing: yield curve classification, message formatting, and the
self-rescheduling job (port of FlowCore's "Mercado" feed)."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from investments.daily_briefing import (
    BriefingSnapshot,
    Quote,
    _classify_shape,
    _classify_state,
    format_briefing_message,
)
from investments.jobs import DAILY_BRIEFING_JOB_NAME
from jobs.service import JobService
from jobs.worker import JobWorker
from models.job import JobStatus
from repositories.job import JobRepository


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def worker(session_factory, monkeypatch):
    monkeypatch.setattr("jobs.worker.async_session_factory", session_factory)
    return JobWorker()


@pytest.fixture(autouse=True)
def _always_pregao(monkeypatch):
    monkeypatch.setattr("investments.jobs.is_pregao_now", lambda: True)


# ── curve classification ─────────────────────────────────────────────────────


def test_classify_state_inverted():
    assert _classify_state(-5.0, None) == "inverted"


def test_classify_state_insufficient_data():
    assert _classify_state(None, None) == "insufficient_data"


def test_classify_state_steepening():
    assert _classify_state(120.0, 100.0) == "steepening"


def test_classify_shape_needs_two_prior_points():
    assert _classify_shape({"treasury": 4.0, "treasury_2y": 3.5}, {"treasury": 4.0}) == (None, None)


def test_classify_shape_bear_steepening():
    points = {"treasury": 4.20, "treasury_2y": 3.50, "treasury_30y": 4.50}
    prev = {"treasury": 4.00, "treasury_2y": 3.55, "treasury_30y": 4.25}
    shape, interpretation = _classify_shape(points, prev)
    assert shape == "bear_steepening"
    assert interpretation is not None


# ── format_briefing_message ──────────────────────────────────────────────────


def test_format_briefing_message_includes_sections():
    snapshot = BriefingSnapshot(
        quotes={
            "dollar": Quote("dollar", "fx", "USDBRL=X", "price", 5.40, 5.35, 0.93),
            "dxy": Quote("dxy", "fx", "DX-Y.NYB", "price", 100.0, 99.0, 1.01),
            "sp500": Quote("sp500", "equities", "^GSPC", "price", 5000.0, 4900.0, 2.04),
        },
        curve=None,
    )
    message = format_briefing_message(snapshot)
    assert "RADAR DE MERCADO" in message
    assert "DÓLAR" in message
    assert "EQUITIES" in message.upper()


# ── send_daily_briefing_job ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_daily_briefing_job_sends_when_number_configured(session_factory, worker, monkeypatch):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "market_alert_whatsapp_number", "5511999999999")

    fake_snapshot = BriefingSnapshot(
        quotes={"dollar": Quote("dollar", "fx", "USDBRL=X", "price", 5.40, 5.35, 0.93)}, curve=None
    )

    async def _fake_fetch():
        return fake_snapshot

    monkeypatch.setattr("investments.jobs.fetch_briefing_snapshot", _fake_fetch)

    async with session_factory() as session:
        await JobService(session).enqueue(DAILY_BRIEFING_JOB_NAME, {})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        sent = await JobRepository(session).find_one(name="whatsapp.send_text")
        assert sent is not None
        assert sent.payload["to"] == "5511999999999"

        rescheduled = await JobRepository(session).find_one(name=DAILY_BRIEFING_JOB_NAME, status=JobStatus.QUEUED)
        assert rescheduled is not None


@pytest.mark.asyncio
async def test_daily_briefing_job_skips_when_no_tickers_resolved(session_factory, worker, monkeypatch):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "market_alert_whatsapp_number", "5511999999999")

    async def _fake_fetch():
        return BriefingSnapshot(quotes={}, curve=None)

    monkeypatch.setattr("investments.jobs.fetch_briefing_snapshot", _fake_fetch)

    async with session_factory() as session:
        await JobService(session).enqueue(DAILY_BRIEFING_JOB_NAME, {})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        sent = await JobRepository(session).find_one(name="whatsapp.send_text")
        assert sent is None
