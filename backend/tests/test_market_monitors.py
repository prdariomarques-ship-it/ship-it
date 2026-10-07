"""Market monitors: Bollinger math, pregão gate, and the self-rescheduling
jobs on the isolated financial worker — delivery goes through
telegram.send_message, which looks up each feed's bot/chat from settings
at execution time (never stored in payload)."""
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from investments.b3_calendar import is_pregao_now
from investments.b3_summary import B3Summary
from investments.jobs import (
    B3_SUMMARY_JOB_NAME,
    SPCX34_JOB_NAME,
    TELEGRAM_SEND_JOB_NAME,
    seed_financial_monitor_jobs,
)
from investments.models import FinancialJobStatus
from investments.repository import FinancialJobRepository
from investments.spcx34_monitor import MarketDataError, SPCX34Check, bollinger_upper_band
from investments.worker import FinancialWorker


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def worker(session_factory, monkeypatch):
    monkeypatch.setattr("investments.worker.async_session_factory", session_factory)
    return FinancialWorker()


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


# ── is_pregao_now: B3 holiday calendar ───────────────────────────────────────


def test_pregao_false_on_fixed_date_national_holiday():
    from zoneinfo import ZoneInfo

    independencia = datetime(2026, 9, 7, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))  # Monday
    assert is_pregao_now(independencia) is False


def test_pregao_false_on_computed_carnaval():
    from zoneinfo import ZoneInfo

    # Carnaval 2026: Monday Feb 16 / Tuesday Feb 17 (Easter 2026 = Apr 5).
    carnaval_monday = datetime(2026, 2, 16, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    carnaval_tuesday = datetime(2026, 2, 17, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert is_pregao_now(carnaval_monday) is False
    assert is_pregao_now(carnaval_tuesday) is False


def test_pregao_false_on_computed_good_friday():
    from zoneinfo import ZoneInfo

    good_friday_2026 = datetime(2026, 4, 3, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert is_pregao_now(good_friday_2026) is False


def test_pregao_true_the_day_right_after_a_holiday():
    """The gate must not over-block — the very next trading day (a normal
    Wednesday, no longer Carnaval) must pass again."""
    from zoneinfo import ZoneInfo

    ash_wednesday_2026 = datetime(2026, 2, 18, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert is_pregao_now(ash_wednesday_2026) is True


# ── check_spcx34_job / send_b3_summary_job ────────────────────────────────────


@pytest.fixture(autouse=True)
def _always_pregao(monkeypatch):
    monkeypatch.setattr("investments.jobs.is_pregao_now", lambda: True)


@pytest.fixture(autouse=True)
def _monitors_enabled(monkeypatch):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "market_monitors_enabled", True)


@pytest.mark.asyncio
async def test_check_spcx34_job_enqueues_telegram_message_when_triggered(session_factory, worker, monkeypatch):
    async def _fake_check(ticker, window, std_mult):
        return SPCX34Check(ticker=ticker, price=60.0, upper_band=57.74, triggered=True, quote_timestamp=1_700_000_000, quote_age_hours=1.0)

    monkeypatch.setattr("investments.jobs.check_spcx34", _fake_check)

    async with session_factory() as session:
        await FinancialJobRepository(session).create(name=SPCX34_JOB_NAME, payload={})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        sent = await FinancialJobRepository(session).find_one(name=TELEGRAM_SEND_JOB_NAME)
        assert sent is not None
        assert sent.payload["feed"] == "spcx"
        assert "60.00" in sent.payload["text"]

        rescheduled = await FinancialJobRepository(session).find_one(
            name=SPCX34_JOB_NAME, status=FinancialJobStatus.QUEUED
        )
        assert rescheduled is not None


@pytest.mark.asyncio
async def test_check_spcx34_alert_declares_age_when_quote_is_stale(session_factory, worker, monkeypatch):
    async def _fake_check(ticker, window, std_mult):
        return SPCX34Check(
            ticker=ticker, price=60.0, upper_band=57.74, triggered=True,
            quote_timestamp=1_700_000_000, quote_age_hours=30.0,  # past FRESH_ENOUGH_HOURS
        )

    monkeypatch.setattr("investments.jobs.check_spcx34", _fake_check)

    async with session_factory() as session:
        await FinancialJobRepository(session).create(name=SPCX34_JOB_NAME, payload={})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        sent = await FinancialJobRepository(session).find_one(name=TELEGRAM_SEND_JOB_NAME)
        assert "30h" in sent.payload["text"]
        assert "pregão de hoje não confirmado" in sent.payload["text"]


@pytest.mark.asyncio
async def test_check_spcx34_job_sends_nothing_when_not_triggered(session_factory, worker, monkeypatch):
    async def _fake_check(ticker, window, std_mult):
        return SPCX34Check(ticker=ticker, price=50.0, upper_band=57.74, triggered=False, quote_timestamp=1_700_000_000, quote_age_hours=1.0)

    monkeypatch.setattr("investments.jobs.check_spcx34", _fake_check)

    async with session_factory() as session:
        await FinancialJobRepository(session).create(name=SPCX34_JOB_NAME, payload={})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        sent = await FinancialJobRepository(session).find_one(name=TELEGRAM_SEND_JOB_NAME)
        assert sent is None


@pytest.mark.asyncio
async def test_check_spcx34_job_reschedules_even_on_market_data_error(session_factory, worker, monkeypatch):
    async def _fake_check(ticker, window, std_mult):
        raise MarketDataError("yahoo is down")

    monkeypatch.setattr("investments.jobs.check_spcx34", _fake_check)

    async with session_factory() as session:
        await FinancialJobRepository(session).create(name=SPCX34_JOB_NAME, payload={})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        rescheduled = await FinancialJobRepository(session).find_one(
            name=SPCX34_JOB_NAME, status=FinancialJobStatus.QUEUED
        )
        assert rescheduled is not None


@pytest.mark.asyncio
async def test_check_spcx34_job_reschedules_even_on_unexpected_exception(session_factory, worker, monkeypatch):
    """The dual-chain bug this guards against: an unexpected (non-MarketDataError)
    exception must still only leave ONE queued row for this job name — the
    handler must never let it escape to the worker's own retry mechanism
    while the `finally` reschedule also fires."""
    async def _fake_check(ticker, window, std_mult):
        raise ValueError("something nobody anticipated")

    monkeypatch.setattr("investments.jobs.check_spcx34", _fake_check)

    async with session_factory() as session:
        await FinancialJobRepository(session).create(name=SPCX34_JOB_NAME, payload={})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        from sqlalchemy import select

        from investments.models import FinancialJob

        rows = (
            await session.execute(select(FinancialJob).where(FinancialJob.name == SPCX34_JOB_NAME))
        ).scalars().all()
        # The original run (terminal, SUCCEEDED despite the caught exception)
        # plus exactly one new chain — never two competing QUEUED/RUNNING rows.
        queued = [r for r in rows if r.status == FinancialJobStatus.QUEUED]
        assert len(queued) == 1


@pytest.mark.asyncio
async def test_seed_financial_monitor_jobs_is_idempotent(session_factory):
    async with session_factory() as session:
        await seed_financial_monitor_jobs(session)
    async with session_factory() as session:
        await seed_financial_monitor_jobs(session)  # second call: DuplicateChainError caught internally

    async with session_factory() as session:
        from sqlalchemy import select

        from investments.models import FinancialJob

        for job_name in (SPCX34_JOB_NAME, B3_SUMMARY_JOB_NAME):
            result = await session.execute(select(FinancialJob).where(FinancialJob.name == job_name))
            assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_seed_financial_monitor_jobs_noop_when_disabled(session_factory, monkeypatch):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "market_monitors_enabled", False)

    async with session_factory() as session:
        await seed_financial_monitor_jobs(session)

    async with session_factory() as session:
        from sqlalchemy import select

        from investments.models import FinancialJob

        result = await session.execute(select(FinancialJob).where(FinancialJob.name == SPCX34_JOB_NAME))
        assert result.scalars().all() == []


# ── send_b3_summary_job (PMX / @dariozcodebot port) ──────────────────────────


def test_format_b3_summary_message_declares_age_when_stale():
    from investments.b3_summary import format_b3_summary_message

    summary = B3Summary(
        ibovespa_points=166934.2, ibovespa_delta_pct=1.23,
        usdbrl_level=5.4321, usdbrl_delta_pct=-0.5, max_age_hours=50.0,
    )
    message = format_b3_summary_message(summary)
    assert "50h" in message
    assert "pregão de hoje não confirmado" in message


def test_format_b3_summary_message_silent_when_fresh():
    from investments.b3_summary import format_b3_summary_message

    summary = B3Summary(
        ibovespa_points=166934.2, ibovespa_delta_pct=1.23,
        usdbrl_level=5.4321, usdbrl_delta_pct=-0.5, max_age_hours=1.0,
    )
    message = format_b3_summary_message(summary)
    assert "pregão de hoje não confirmado" not in message


@pytest.mark.asyncio
async def test_b3_summary_job_enqueues_telegram_message(session_factory, worker, monkeypatch):
    async def _fake_check():
        return B3Summary(ibovespa_points=166934.2, ibovespa_delta_pct=1.23, usdbrl_level=5.4321, usdbrl_delta_pct=-0.5, max_age_hours=1.0)

    monkeypatch.setattr("investments.jobs.check_b3_summary", _fake_check)

    async with session_factory() as session:
        await FinancialJobRepository(session).create(name=B3_SUMMARY_JOB_NAME, payload={})

    assert await worker.run_once() == 1

    async with session_factory() as session:
        sent = await FinancialJobRepository(session).find_one(name=TELEGRAM_SEND_JOB_NAME)
        assert sent is not None
        assert sent.payload["feed"] == "b3"
        assert "166.934" in sent.payload["text"]
        assert "5.4321" in sent.payload["text"]

        rescheduled = await FinancialJobRepository(session).find_one(
            name=B3_SUMMARY_JOB_NAME, status=FinancialJobStatus.QUEUED
        )
        assert rescheduled is not None


# ── send_telegram_message_job: disablement, credentials, delivery outcome ───


@pytest.mark.asyncio
async def test_telegram_send_job_sends_when_feed_configured(session_factory, worker, monkeypatch):
    from utils.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_bot_token_spcx", "tok")
    monkeypatch.setattr(settings, "telegram_chat_id_spcx", "chat-1")

    sent_calls = []

    async def _fake_send(token, chat_id, text):
        sent_calls.append((token, chat_id, text))
        return {"message_id": 7}

    monkeypatch.setattr("investments.jobs.send_telegram_message", _fake_send)

    async with session_factory() as session:
        await FinancialJobRepository(session).create(
            name=TELEGRAM_SEND_JOB_NAME, payload={"feed": "spcx", "text": "oi"}
        )

    assert await worker.run_once() == 1
    assert sent_calls == [("tok", "chat-1", "oi")]

    async with session_factory() as session:
        job = await FinancialJobRepository(session).find_one(name=TELEGRAM_SEND_JOB_NAME)
        assert job.result == {"delivered": True, "message_id": 7}


@pytest.mark.asyncio
async def test_telegram_send_job_skips_when_feed_not_configured(session_factory, worker, monkeypatch):
    sent_calls = []

    async def _fake_send(token, chat_id, text):
        sent_calls.append((token, chat_id, text))
        return {}

    monkeypatch.setattr("investments.jobs.send_telegram_message", _fake_send)

    async with session_factory() as session:
        await FinancialJobRepository(session).create(
            name=TELEGRAM_SEND_JOB_NAME, payload={"feed": "spcx", "text": "oi"}
        )

    assert await worker.run_once() == 1
    assert sent_calls == []

    async with session_factory() as session:
        job = await FinancialJobRepository(session).find_one(name=TELEGRAM_SEND_JOB_NAME)
        # Completed, but result says plainly it was never sent — the thing
        # the review flagged: a skip must never look like a delivered SUCCEEDED.
        assert job.status == FinancialJobStatus.SUCCEEDED
        assert job.result == {"delivered": False, "reason": "missing_credential"}


@pytest.mark.asyncio
async def test_telegram_send_job_blocked_when_monitors_disabled_even_if_already_queued(
    session_factory, worker, monkeypatch
):
    """The exact bug the review caught: MARKET_MONITORS_ENABLED=false must
    stop a telegram.send_message job that was already queued before the
    flag flipped — not just prevent new check cycles."""
    from utils.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_bot_token_spcx", "tok")
    monkeypatch.setattr(settings, "telegram_chat_id_spcx", "chat-1")

    sent_calls = []

    async def _fake_send(token, chat_id, text):
        sent_calls.append((token, chat_id, text))
        return {"message_id": 1}

    monkeypatch.setattr("investments.jobs.send_telegram_message", _fake_send)

    async with session_factory() as session:
        await FinancialJobRepository(session).create(
            name=TELEGRAM_SEND_JOB_NAME, payload={"feed": "spcx", "text": "oi"}
        )

    # Disabled AFTER the send was already queued.
    monkeypatch.setattr(settings, "market_monitors_enabled", False)

    assert await worker.run_once() == 1
    assert sent_calls == []  # never actually called send_telegram_message

    async with session_factory() as session:
        job = await FinancialJobRepository(session).find_one(name=TELEGRAM_SEND_JOB_NAME)
        assert job.status == FinancialJobStatus.SUCCEEDED
        assert job.result == {"delivered": False, "reason": "monitors_disabled"}
