"""Standalone entry point for the financial-monitor worker.

Run as `python -m investments` — its own process, its own event loop, no
FastAPI, no uvicorn, nothing imported from jobs.*/main.py. This is the
isolation boundary: the WhatsApp request-handling process can crash, hang
or get rebuilt without this process ever noticing, and vice versa.
"""
import asyncio
import signal

from database.session import async_session_factory
from investments.jobs import seed_financial_monitor_jobs  # noqa: F401 - registers handlers via investments.jobs
from investments.worker import financial_worker
from utils.config import get_settings
from utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(json_output=settings.log_json)
    logger.info("Financial worker process starting (monitors_enabled=%s)", settings.market_monitors_enabled)

    async with async_session_factory() as session:
        await seed_financial_monitor_jobs(session)
        await session.commit()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    financial_worker.start()
    await stop_event.wait()
    logger.info("Financial worker process stopping")
    await financial_worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
