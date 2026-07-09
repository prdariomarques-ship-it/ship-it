"""Job lifecycle events: published on Redis pub/sub and persisted to the logs table."""
import json
from datetime import datetime, timezone

from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from models.job import Job
from services.audit import record_log
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class JobEventPublisher:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._redis: aioredis.Redis | None = None
        self._redis_available = True

    async def publish(self, db: AsyncSession, job: Job, event: str, detail: str = "") -> None:
        payload = {
            "event": event,
            "job_id": job.id,
            "job_name": job.name,
            "attempts": job.attempts,
            "status": job.status.value,
            "detail": detail,
            "at": datetime.now(timezone.utc).isoformat(),
        }

        level = "error" if event == "failed" else "info"
        await record_log(db, source=f"job:{job.name}", message=f"Job {job.id} {event}",
                         level=level, payload=payload)

        if not self._redis_available:
            return
        try:
            if self._redis is None:
                self._redis = aioredis.from_url(self._settings.redis_url, decode_responses=True)
            await self._redis.publish(self._settings.jobs_events_channel, json.dumps(payload))
        except Exception:  # noqa: BLE001 - events must never break job execution
            logger.warning("Redis unavailable; job events limited to the logs table")
            self._redis_available = False


job_event_publisher = JobEventPublisher()
