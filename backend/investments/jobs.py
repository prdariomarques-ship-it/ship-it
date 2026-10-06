"""Financial monitor jobs — registered on the isolated FinancialWorker
(investments/worker.py), never on jobs.registry/jobs.worker. Each
self-rescheduling check (SPCX34, B3 summary, daily briefing) runs once,
then returns Reschedule(...) to re-arm itself with a delay — applied by
the worker only after the current row is already terminal, and never lets
an unexpected exception escape the handler, so the worker's own
retry/backoff can never fire *in addition to* that reschedule and spawn a
second chain. The unique partial index on financial_jobs.name (see
models.py) is the second, DB-enforced line of defense against the same
thing — and the reason the reschedule can't just happen inside the
handler itself (its own row is still RUNNING at that point).

market_monitors_enabled is checked both before scheduling a check AND
inside send_telegram_message_job itself — disabling it stops delivery of
anything already queued, not just future cycles, and stops a running
chain from re-arming instead of just no-oping forever.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from investments.b3_calendar import is_pregao_now
from investments.b3_summary import check_b3_summary, format_b3_summary_message
from investments.daily_briefing import fetch_briefing_snapshot, format_briefing_message
from investments.models import FinancialJob
from investments.repository import DuplicateChainError, FinancialJobRepository
from investments.spcx34_monitor import check_spcx34
from investments.telegram_sender import (
    TelegramPermanentError,
    TelegramUncertainOutcomeError,
    send_telegram_message,
)
from investments.worker import Reschedule, financial_job_handler
from investments.yahoo_finance import MarketDataError
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

SPCX34_JOB_NAME = "market.check_spcx34"
B3_SUMMARY_JOB_NAME = "market.send_b3_summary"
DAILY_BRIEFING_JOB_NAME = "market.send_daily_briefing"
TELEGRAM_SEND_JOB_NAME = "telegram.send_message"

CHAIN_JOB_NAMES = (SPCX34_JOB_NAME, B3_SUMMARY_JOB_NAME, DAILY_BRIEFING_JOB_NAME)

# feed name -> (bot token setting, chat id setting) on Settings.
_FEED_CREDENTIALS = {
    "spcx": ("telegram_bot_token_spcx", "telegram_chat_id_spcx"),
    "b3": ("telegram_bot_token_b3", "telegram_chat_id_b3"),
    "mercado": ("telegram_bot_token_mercado", "telegram_chat_id_mercado"),
}


async def _enqueue_telegram(db: AsyncSession, feed: str, text: str) -> None:
    # telegram.send_message is NOT self-rescheduling (no unique constraint
    # concern) — a burst of real alerts for the same feed must be allowed
    # to queue up as separate rows, not collapse into one.
    job = FinancialJob(name=TELEGRAM_SEND_JOB_NAME, payload={"feed": feed, "text": text}, max_attempts=3)
    db.add(job)
    await db.commit()


@financial_job_handler(TELEGRAM_SEND_JOB_NAME)
async def send_telegram_message_job(db: AsyncSession, payload: dict) -> dict:
    feed = payload["feed"]
    text = payload["text"]
    settings = get_settings()

    if not settings.market_monitors_enabled:
        logger.info("Telegram send for feed %r skipped: monitors disabled.", feed)
        return {"delivered": False, "reason": "monitors_disabled"}

    token_field, chat_field = _FEED_CREDENTIALS[feed]
    token = getattr(settings, token_field)
    chat_id = getattr(settings, chat_field)
    if not token or not chat_id:
        logger.warning(
            "Telegram feed %r not configured (%s/%s missing) — message not sent.",
            feed, token_field.upper(), chat_field.upper(),
        )
        return {"delivered": False, "reason": "missing_credential"}

    try:
        result = await send_telegram_message(token, chat_id, text)
    except TelegramPermanentError as exc:
        # Will never succeed on retry (bad chat, bot blocked, ...) — record
        # it and stop, rather than let the generic retry hammer it.
        logger.error("Telegram send for feed %r failed permanently: %s", feed, exc)
        return {"delivered": False, "reason": "permanent_error", "detail": str(exc)}
    except TelegramUncertainOutcomeError as exc:
        # Unknown whether Telegram actually received this — do NOT retry
        # automatically (that could double-send); surface it for a human.
        logger.error("Telegram send for feed %r has an uncertain outcome: %s", feed, exc)
        return {"delivered": None, "reason": "uncertain_outcome", "detail": str(exc)}
    # TelegramRateLimitedError is allowed to propagate — the worker's
    # retry/backoff (which reads exc.retry_after_seconds) handles it.

    return {"delivered": True, "message_id": result.get("message_id")}


@financial_job_handler(SPCX34_JOB_NAME)
async def check_spcx34_job(db: AsyncSession, payload: dict) -> Reschedule | None:
    settings = get_settings()
    if not settings.market_monitors_enabled:
        return None  # chain intentionally ends, not an error
    try:
        if is_pregao_now():
            await _run_spcx34_check(db, settings)
    except Exception:  # noqa: BLE001 - never let this escape; see module docstring
        logger.exception("SPCX34 check raised unexpectedly")
    return Reschedule(delay_seconds=settings.market_check_interval_seconds)


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

    message = (
        "🚨 <b>ALERTA SPCX34.SA</b>\n"
        f"Preço: R$ {result.price:.2f}\n"
        f"Acima da banda superior (R$ {result.upper_band:.2f})"
    )
    await _enqueue_telegram(db, "spcx", message)


@financial_job_handler(B3_SUMMARY_JOB_NAME)
async def send_b3_summary_job(db: AsyncSession, payload: dict) -> Reschedule | None:
    """Port of the original FlowCore PMX (@dariozcodebot) feed: IBOVESPA +
    USD/BRL, sent every check during pregão — a radar, not a threshold alert."""
    settings = get_settings()
    if not settings.market_monitors_enabled:
        return None
    try:
        if is_pregao_now():
            await _run_b3_summary(db, settings)
    except Exception:  # noqa: BLE001 - never let this escape; see module docstring
        logger.exception("B3 summary raised unexpectedly")
    return Reschedule(delay_seconds=settings.market_check_interval_seconds)


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
    await _enqueue_telegram(db, "b3", format_b3_summary_message(summary))


@financial_job_handler(DAILY_BRIEFING_JOB_NAME)
async def send_daily_briefing_job(db: AsyncSession, payload: dict) -> Reschedule | None:
    """Port of the original FlowCore "Mercado" feed: yield curve + FX +
    equities + commodities, sent every check during pregão. Macro regime
    and active-alerts sections are not ported (see investments/daily_briefing.py)."""
    settings = get_settings()
    if not settings.market_monitors_enabled:
        return None
    try:
        if is_pregao_now():
            await _run_daily_briefing(db, settings)
    except Exception:  # noqa: BLE001 - never let this escape; see module docstring
        logger.exception("Daily briefing raised unexpectedly")
    return Reschedule(delay_seconds=settings.market_check_interval_seconds)


async def _run_daily_briefing(db: AsyncSession, settings) -> None:
    snapshot = await fetch_briefing_snapshot()
    if not snapshot.quotes:
        logger.warning("Daily briefing skipped: no tickers returned real data")
        return

    logger.info("Daily briefing: %d tickers resolved", len(snapshot.quotes))
    await _enqueue_telegram(db, "mercado", format_briefing_message(snapshot))


async def seed_financial_monitor_jobs(db: AsyncSession) -> None:
    """Enqueue the first run of each monitor chain — safe to call on every
    process start: a DuplicateChainError (another instance already seeded)
    is expected and ignored, not an error. A no-op while
    market_monitors_enabled is false (the default)."""
    settings = get_settings()
    if not settings.market_monitors_enabled:
        return
    repository = FinancialJobRepository(db)
    for job_name in CHAIN_JOB_NAMES:
        try:
            await repository.create(name=job_name, payload={})
            logger.info("Seeded financial monitor job %s", job_name)
        except DuplicateChainError:
            pass
