"""Market monitor jobs — self-rescheduling through the durable job queue (no
external cron needed). Each handler checks once, then re-enqueues itself with
a delay, so the chain keeps itself alive across worker restarts and retries.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from investments.b3_calendar import is_pregao_now
from investments.b3_summary import check_b3_summary, format_b3_summary_message
from investments.daily_briefing import fetch_briefing_snapshot, format_briefing_message
from investments.spcx34_monitor import check_spcx34
from investments.yahoo_finance import MarketDataError
from jobs.registry import job_handler
from jobs.service import JobService
from models.job import JobStatus
from repositories.job import JobRepository
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

SPCX34_JOB_NAME = "market.check_spcx34"
B3_SUMMARY_JOB_NAME = "market.send_b3_summary"
DAILY_BRIEFING_JOB_NAME = "market.send_daily_briefing"


@job_handler(SPCX34_JOB_NAME)
async def check_spcx34_job(db: AsyncSession, payload: dict) -> None:
    settings = get_settings()
    try:
        if settings.market_monitors_enabled and is_pregao_now():
            await _run_spcx34_check(db, settings)
    finally:
        # Keep the periodic chain alive regardless of outcome — a bad fetch
        # or a closed market today must not silently end future checks.
        if settings.market_monitors_enabled:
            await JobService(db).enqueue(
                SPCX34_JOB_NAME, {}, delay_seconds=settings.market_check_interval_seconds
            )


async def _run_spcx34_check(db: AsyncSession, settings) -> None:
    try:
        result = await check_spcx34(
            settings.spcx34_ticker, settings.spcx34_bollinger_window, settings.spcx34_bollinger_std_mult
        )
    except MarketDataError as exc:
        logger.warning("SPCX34 check skipped (no real data): %s", exc)
        return

    logger.info(
        "SPCX34 check: price=%.2f upper_band=%.2f triggered=%s",
        result.price, result.upper_band, result.triggered,
    )
    if not result.triggered:
        return

    if not settings.market_alert_whatsapp_number:
        logger.warning(
            "SPCX34 breakout detected (price=%.2f > band=%.2f) but "
            "MARKET_ALERT_WHATSAPP_NUMBER is not configured — no alert sent.",
            result.price, result.upper_band,
        )
        return

    message = (
        "🚨 ALERTA SPCX34.SA\n"
        f"Preço: R$ {result.price:.2f}\n"
        f"Acima da banda superior (R$ {result.upper_band:.2f})"
    )
    await JobService(db).enqueue(
        "whatsapp.send_text", {"to": settings.market_alert_whatsapp_number, "content": message}
    )


@job_handler(B3_SUMMARY_JOB_NAME)
async def send_b3_summary_job(db: AsyncSession, payload: dict) -> None:
    """Port of the original FlowCore PMX (@dariozcodebot) feed: IBOVESPA +
    USD/BRL, sent every check during pregão — a radar, not a threshold alert."""
    settings = get_settings()
    try:
        if settings.market_monitors_enabled and is_pregao_now():
            await _run_b3_summary(db, settings)
    finally:
        if settings.market_monitors_enabled:
            await JobService(db).enqueue(
                B3_SUMMARY_JOB_NAME, {}, delay_seconds=settings.market_check_interval_seconds
            )


async def _run_b3_summary(db: AsyncSession, settings) -> None:
    try:
        summary = await check_b3_summary()
    except MarketDataError as exc:
        logger.warning("B3 summary skipped (no real data): %s", exc)
        return

    logger.info(
        "B3 summary: ibovespa=%.0f (%s) usdbrl=%.4f (%s)",
        summary.ibovespa_points, summary.ibovespa_delta_pct,
        summary.usdbrl_level, summary.usdbrl_delta_pct,
    )

    if not settings.market_alert_whatsapp_number:
        logger.warning("B3 summary ready but MARKET_ALERT_WHATSAPP_NUMBER is not configured — not sent.")
        return

    await JobService(db).enqueue(
        "whatsapp.send_text",
        {"to": settings.market_alert_whatsapp_number, "content": format_b3_summary_message(summary)},
    )


@job_handler(DAILY_BRIEFING_JOB_NAME)
async def send_daily_briefing_job(db: AsyncSession, payload: dict) -> None:
    """Port of the original FlowCore "Mercado" feed: yield curve + FX +
    equities + commodities, sent every check during pregão. Macro regime
    and active-alerts sections are not ported (see investments/daily_briefing.py)."""
    settings = get_settings()
    try:
        if settings.market_monitors_enabled and is_pregao_now():
            await _run_daily_briefing(db, settings)
    finally:
        if settings.market_monitors_enabled:
            await JobService(db).enqueue(
                DAILY_BRIEFING_JOB_NAME, {}, delay_seconds=settings.market_check_interval_seconds
            )


async def _run_daily_briefing(db: AsyncSession, settings) -> None:
    snapshot = await fetch_briefing_snapshot()
    if not snapshot.quotes:
        logger.warning("Daily briefing skipped: no tickers returned real data")
        return

    logger.info("Daily briefing: %d tickers resolved", len(snapshot.quotes))

    if not settings.market_alert_whatsapp_number:
        logger.warning("Daily briefing ready but MARKET_ALERT_WHATSAPP_NUMBER is not configured — not sent.")
        return

    await JobService(db).enqueue(
        "whatsapp.send_text",
        {"to": settings.market_alert_whatsapp_number, "content": format_briefing_message(snapshot)},
    )


async def seed_market_monitor_jobs(db: AsyncSession) -> None:
    """Enqueue the first run of each monitor if no instance of its chain is
    already queued/running — called once on app startup so restarts never
    spawn parallel chains."""
    settings = get_settings()
    if not settings.market_monitors_enabled:
        return
    repository = JobRepository(db)
    for job_name in (SPCX34_JOB_NAME, B3_SUMMARY_JOB_NAME, DAILY_BRIEFING_JOB_NAME):
        existing = await repository.find_one(name=job_name, status=JobStatus.QUEUED)
        if existing is None:
            existing = await repository.find_one(name=job_name, status=JobStatus.RUNNING)
        if existing is None:
            await JobService(db).enqueue(job_name, {})
            logger.info("Seeded market monitor job %s", job_name)
