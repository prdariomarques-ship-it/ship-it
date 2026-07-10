"""Fixed-window rate limiting backed by Redis, with in-memory fallback.

The in-memory fallback keeps development and tests working without Redis;
in production Redis makes the limit shared across workers.
"""
import time

from redis import asyncio as aioredis

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._redis: aioredis.Redis | None = None
        self._redis_available = True
        self._local_windows: dict[str, tuple[int, int]] = {}  # key -> (window_start, count)

    def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._settings.redis_url, decode_responses=True)
        return self._redis

    async def is_allowed(
        self, identifier: str, limit: int | None = None, window_seconds: int | None = None
    ) -> bool:
        """Fixed-window check. Pass limit/window_seconds to use a different
        threshold than the global HTTP one for this identifier's namespace
        (e.g. a per-contact auto-reply throttle) — callers must stay
        consistent about which namespace uses which threshold, since the
        window key itself doesn't encode the limit."""
        limit = limit if limit is not None else self._settings.rate_limit_requests
        window = window_seconds if window_seconds is not None else self._settings.rate_limit_window_seconds
        key = f"ratelimit:{identifier}:{int(time.time()) // window}"

        if self._redis_available:
            try:
                redis = self._get_redis()
                count = await redis.incr(key)
                if count == 1:
                    await redis.expire(key, window)
                return count <= limit
            except Exception:  # noqa: BLE001 - any Redis failure falls back to local
                logger.warning("Redis unavailable, falling back to in-memory rate limiting")
                self._redis_available = False

        window_start = int(time.time()) // window
        if len(self._local_windows) > 10_000:
            # Drop stale windows so a rotating set of client IPs can't grow memory.
            self._local_windows = {
                key: value for key, value in self._local_windows.items() if value[0] == window_start
            }
        current = self._local_windows.get(identifier)
        if current is None or current[0] != window_start:
            self._local_windows[identifier] = (window_start, 1)
            return True
        self._local_windows[identifier] = (window_start, current[1] + 1)
        return current[1] + 1 <= limit


rate_limiter = RateLimiter()
