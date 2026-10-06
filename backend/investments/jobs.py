"""Market monitor jobs — self-rescheduling through the durable job queue (no
external cron needed). Each handler checks once, then re-enqueues itself with
a delay, so the chain keeps itself alive across worker restarts and retries.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from investments.b3_calendar import is_pregao_now
from investments.spcx34_monitor import MarketDataError, check_spcx34
from jobs.registry import job_handler
from jobs.service import JobService
from models.job import JobStatus
from repositories.job import JobRepository
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

SPCX34_JOB_NAME = "market.check_spcx34"


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


async def seed_market_monitor_jobs(db: AsyncSession) -> None:
    """Enqueue the first run of each monitor if no instance of its chain is
    already queued/running — called once on app startup so restarts never
    spawn parallel chains."""
    settings = get_settings()
    if not settings.market_monitors_enabled:
        return
    repository = JobRepository(db)
    existing = await repository.find_one(name=SPCX34_JOB_NAME, status=JobStatus.QUEUED)
    if existing is None:
        existing = await repository.find_one(name=SPCX34_JOB_NAME, status=JobStatus.RUNNING)
    if existing is None:
        await JobService(db).enqueue(SPCX34_JOB_NAME, {})
        logger.info("Seeded market monitor job %s", SPCX34_JOB_NAME)
