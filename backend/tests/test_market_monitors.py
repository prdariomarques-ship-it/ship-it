"""Market monitors: Bollinger math, pregão gate, and the self-rescheduling job."""
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from investments.b3_calendar import is_pregao_now
from investments.b3_summary import B3Summary
from investments.jobs import B3_SUMMARY_JOB_NAME, SPCX34_JOB_NAME, seed_market_monitor_jobs
from investments.spcx34_monitor import MarketDataError, SPCX34Check, bollinger_upper_band
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


# ── bollinger_upper_band ────────────────────────────────────────────────────


def test_bollinger_upper_band_known_values():
    closes = [10.0] * 19 + [12.0]  # mean != all-equal, non-zero stdev
    upper = bollinger_upper_band(closes, window=20, std_mult=2.0)
    assert upper > 10.0  # above the flat baseline, since the last close jumped


def test_bollinger_upper_band_not_enough_data():
    with pytest.raises(MarketDataError):
        bollinger_upper_band([1.0, 2.0], window=20, std_mult=2.0)


# ── is_pregao_now ────────────────────────────────────────────────────────────


def test_pregao_weekday_within_hours():
    from zoneinfo import ZoneInfo

    now = datetime(2026, 10, 6, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))  # Tuesday
    assert is_pregao_now(now) is True


def test_pregao_outside_hours():
    from zoneinfo import ZoneInfo
    now = datetime(2026, 10, 6, 21, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert is_pregao_now(now) is False


def test_pregao_weekend():
    from zoneinfo import ZoneInfo
    now = datetime(2026, 10, 4, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))  # Sunday
    assert is_pregao_now(now) is False


# ── check_spcx34_job ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _always_pregao(monkeypatch):
    monkeypatch.setattr("investments.jobs.is_pregao_now", lambda: True)


@pytest.mark.asyncio
async def test_check_spcx34_job_sends_alert_when_triggered_and_number_configured(
    session_factory, worker, monkeypatch
):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "market_alert_whatsapp_number", "5511999999999")

    async def _fake_check(ticker, window, std_mult):
        return SPCX34Check(ticker=ticker, price=60.0, upper_band=57.74, triggered=True)

    monkeypatch.setattr("investments.jobs.check_spcx34", _fake_check)

    async with session_factory() as session:
        await JobService(session).enqueue(SPCX34_JOB_NAME, {})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        jobs = await JobRepository(session).find_one(name="whatsapp.send_text")
        assert jobs is not None
        assert jobs.payload["to"] == "5511999999999"
        assert "60.00" in jobs.payload["content"]

        # The chain re-arms itself.
        rescheduled = await JobRepository(session).find_one(name=SPCX34_JOB_NAME, status=JobStatus.QUEUED)
        assert rescheduled is not None


@pytest.mark.asyncio
async def test_check_spcx34_job_skips_alert_without_configured_number(session_factory, worker, monkeypatch):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "market_alert_whatsapp_number", "")

    async def _fake_check(ticker, window, std_mult):
        return SPCX34Check(ticker=ticker, price=60.0, upper_band=57.74, triggered=True)

    monkeypatch.setattr("investments.jobs.check_spcx34", _fake_check)

    async with session_factory() as session:
        await JobService(session).enqueue(SPCX34_JOB_NAME, {})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        alert = await JobRepository(session).find_one(name="whatsapp.send_text")
        assert alert is None


@pytest.mark.asyncio
async def test_check_spcx34_job_reschedules_even_on_market_data_error(session_factory, worker, monkeypatch):
    async def _fake_check(ticker, window, std_mult):
        raise MarketDataError("yahoo is down")

    monkeypatch.setattr("investments.jobs.check_spcx34", _fake_check)

    async with session_factory() as session:
        await JobService(session).enqueue(SPCX34_JOB_NAME, {})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        rescheduled = await JobRepository(session).find_one(name=SPCX34_JOB_NAME, status=JobStatus.QUEUED)
        assert rescheduled is not None


@pytest.mark.asyncio
async def test_seed_market_monitor_jobs_is_idempotent(session_factory):
    async with session_factory() as session:
        await seed_market_monitor_jobs(session)
        await session.commit()
    async with session_factory() as session:
        await seed_market_monitor_jobs(session)
        await session.commit()

    async with session_factory() as session:
        from sqlalchemy import select
        from models.job import Job

        for job_name in (SPCX34_JOB_NAME, B3_SUMMARY_JOB_NAME):
            result = await session.execute(select(Job).where(Job.name == job_name))
            assert len(result.scalars().all()) == 1


# ── send_b3_summary_job (PMX / @dariozcodebot port) ──────────────────────────


@pytest.mark.asyncio
async def test_b3_summary_job_sends_message_when_number_configured(session_factory, worker, monkeypatch):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "market_alert_whatsapp_number", "5511999999999")

    async def _fake_check():
        return B3Summary(ibovespa_points=166934.2, ibovespa_delta_pct=1.23, usdbrl_level=5.4321, usdbrl_delta_pct=-0.5)

    monkeypatch.setattr("investments.jobs.check_b3_summary", _fake_check)

    async with session_factory() as session:
        await JobService(session).enqueue(B3_SUMMARY_JOB_NAME, {})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        sent = await JobRepository(session).find_one(name="whatsapp.send_text")
        assert sent is not None
        assert sent.payload["to"] == "5511999999999"
        assert "166.934" in sent.payload["content"]
        assert "5.4321" in sent.payload["content"]

        rescheduled = await JobRepository(session).find_one(name=B3_SUMMARY_JOB_NAME, status=JobStatus.QUEUED)
        assert rescheduled is not None


@pytest.mark.asyncio
async def test_b3_summary_job_skips_without_configured_number(session_factory, worker, monkeypatch):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "market_alert_whatsapp_number", "")

    async def _fake_check():
        return B3Summary(ibovespa_points=166934.2, ibovespa_delta_pct=1.23, usdbrl_level=5.4321, usdbrl_delta_pct=-0.5)

    monkeypatch.setattr("investments.jobs.check_b3_summary", _fake_check)

    async with session_factory() as session:
        await JobService(session).enqueue(B3_SUMMARY_JOB_NAME, {})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        sent = await JobRepository(session).find_one(name="whatsapp.send_text")
        assert sent is None
