"""JSON cache backed by Redis, with a TTL-aware in-memory fallback.

The fallback keeps development and tests working without Redis; in production
Redis makes cached values shared across workers.
"""
import json
import time
from typing import Any

from redis import asyncio as aioredis

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class CacheService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._redis: aioredis.Redis | None = None
        self._redis_available = True
        self._local: dict[str, tuple[float, str]] = {}  # key -> (expires_at, json)

    def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._settings.redis_url, decode_responses=True)
        return self._redis

    async def get(self, key: str) -> Any | None:
        if self._redis_available:
            try:
                raw = await self._get_redis().get(key)
                return json.loads(raw) if raw is not None else None
            except Exception:  # noqa: BLE001
                logger.warning("Redis unavailable, falling back to in-memory cache")
                self._redis_available = False

        entry = self._local.get(key)
        if entry is None or entry[0] < time.monotonic():
            self._local.pop(key, None)
            return None
        return json.loads(entry[1])

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._settings.cache_default_ttl_seconds
        raw = json.dumps(value, default=str)

        if self._redis_available:
            try:
                await self._get_redis().set(key, raw, ex=ttl)
                return
            except Exception:  # noqa: BLE001
                logger.warning("Redis unavailable, falling back to in-memory cache")
                self._redis_available = False

        self._local[key] = (time.monotonic() + ttl, raw)

    async def delete(self, key: str) -> None:
        self._local.pop(key, None)
        if self._redis_available:
            try:
                await self._get_redis().delete(key)
            except Exception:  # noqa: BLE001
                self._redis_available = False


cache_service = CacheService()
