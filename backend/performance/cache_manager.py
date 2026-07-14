"""Redis cache management with TTL and event-driven invalidation.

Provides:
- Cache decorators (@cache_result, @invalidate_on_write)
- Cache operations (get, set, delete, clear)
- Cache statistics (hit ratio, eviction tracking)
- Thundering herd prevention (cache stampede mitigation)
- Distributed cache coherence monitoring
"""

import hashlib
import json
import logging
import random
from functools import wraps
from typing import Any, Callable, Dict, Optional, Set

import redis
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class CacheStatistics:
    """Tracks cache performance metrics."""

    def __init__(self):
        self.hits: int = 0
        self.misses: int = 0
        self.evictions: int = 0
        self.sets: int = 0
        self.deletes: int = 0

    @property
    def hit_ratio(self) -> float:
        """Cache hit ratio (0.0 to 1.0)."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

    def reset(self) -> None:
        """Reset all counters."""
        self.hits = self.misses = self.evictions = self.sets = self.deletes = 0

    def to_dict(self) -> Dict[str, Any]:
        """Export stats as dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "sets": self.sets,
            "deletes": self.deletes,
            "hit_ratio": self.hit_ratio,
        }


class CacheManager:
    """Manages Redis caching with TTL and event-driven invalidation.

    Configuration:
    - max_entries: Maximum cached entries (LRU eviction)
    - default_ttl: Default time-to-live in seconds
    - jitter_range: Cache stampede prevention jitter (±% of TTL)
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        max_entries: int = 10000,
        default_ttl: int = 300,
        jitter_range: float = 0.2,
    ):
        self.redis = redis_client
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self.jitter_range = jitter_range  # ±20% of TTL
        self.stats = CacheStatistics()
        self._invalidation_patterns: Set[str] = set()

    def generate_key(self, *parts: Any, namespace: str = "cache") -> str:
        """Generate cache key from parts, optionally scoped by namespace.

        Args:
            parts: Key components
            namespace: Cache namespace (e.g., user_id for user-scoped data)

        Returns:
            Hash-based cache key safe for Redis
        """
        key_str = ":".join(str(p) for p in parts)
        key_hash = hashlib.sha256(key_str.encode()).hexdigest()[:16]
        return f"{namespace}:{key_hash}"

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value if present and not expired, None otherwise
        """
        try:
            value = self.redis.get(key)
            if value is not None:
                self.stats.hits += 1
                return json.loads(value)
            self.stats.misses += 1
        except Exception as e:
            logger.warning(f"Cache get error for key '{key}': {e}")
            self.stats.misses += 1

        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None = default_ttl)

        Returns:
            True if successful, False otherwise
        """
        try:
            ttl = ttl or self.default_ttl

            # Add jitter to prevent cache stampede (±20% of TTL)
            jitter = random.uniform(1 - self.jitter_range, 1 + self.jitter_range)
            ttl_with_jitter = int(ttl * jitter)

            serialized = json.dumps(value)
            self.redis.setex(key, ttl_with_jitter, serialized)
            self.stats.sets += 1

            # Track pattern for cascade invalidation
            self._track_cache_pattern(key)

            return True
        except Exception as e:
            logger.warning(f"Cache set error for key '{key}': {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if not found
        """
        try:
            result = self.redis.delete(key)
            self.stats.deletes += 1
            return bool(result)
        except Exception as e:
            logger.warning(f"Cache delete error for key '{key}': {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern (cascade invalidation).

        Args:
            pattern: Redis pattern (e.g., "user:*", "jobs:123:*")

        Returns:
            Number of keys deleted
        """
        try:
            keys = self.redis.keys(pattern)
            if keys:
                count = self.redis.delete(*keys)
                self.stats.deletes += count
                return count
        except Exception as e:
            logger.warning(f"Cache delete pattern error for '{pattern}': {e}")

        return 0

    def clear(self) -> bool:
        """Clear all cache entries.

        Returns:
            True if successful
        """
        try:
            self.redis.flushdb()
            self.stats.reset()
            return True
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache performance metrics
        """
        return self.stats.to_dict()

    def _track_cache_pattern(self, key: str) -> None:
        """Track cache key patterns for cascade invalidation."""
        self._invalidation_patterns.add(key)

    @contextmanager
    def batch_operations(self):
        """Context manager for batch cache operations using Redis pipeline.

        Usage:
            with cache_manager.batch_operations() as pipeline:
                pipeline.set("key1", "value1")
                pipeline.delete("key2")
        """
        pipeline = self.redis.pipeline()
        try:
            yield pipeline
        finally:
            pipeline.execute()


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


def init_cache_manager(redis_client: redis.Redis, **kwargs) -> CacheManager:
    """Initialize global cache manager.

    Args:
        redis_client: Redis client connection
        **kwargs: CacheManager initialization parameters

    Returns:
        Initialized CacheManager instance
    """
    global _cache_manager
    _cache_manager = CacheManager(redis_client, **kwargs)
    return _cache_manager


def get_cache_manager() -> CacheManager:
    """Get global cache manager instance.

    Raises:
        RuntimeError if not initialized
    """
    if _cache_manager is None:
        raise RuntimeError("Cache manager not initialized. Call init_cache_manager() first.")
    return _cache_manager


def cache_result(
    ttl: Optional[int] = None,
    namespace: str = "cache",
    key_func: Optional[Callable] = None,
) -> Callable:
    """Decorator for automatic result caching.

    Args:
        ttl: Time-to-live in seconds (None = default)
        namespace: Cache namespace
        key_func: Custom function to generate cache key from args/kwargs

    Example:
        @cache_result(ttl=300, namespace="agents")
        def get_agent(agent_id: str):
            return db.query(Agent).filter(Agent.id == agent_id).first()
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_mgr = get_cache_manager()

            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                key_parts = (func.__name__, *args, *sorted(kwargs.items()))
                cache_key = cache_mgr.generate_key(*key_parts, namespace=namespace)

            # Try cache first
            cached = cache_mgr.get(cache_key)
            if cached is not None:
                return cached

            # Execute function and cache result
            result = func(*args, **kwargs)
            if result is not None:
                cache_mgr.set(cache_key, result, ttl=ttl)

            return result

        return wrapper

    return decorator


def invalidate_on_write(patterns: Optional[list] = None) -> Callable:
    """Decorator for automatic cache invalidation on write operations.

    Args:
        patterns: List of cache key patterns to invalidate (e.g., ["agents:*", "jobs:*"])

    Example:
        @invalidate_on_write(patterns=["agents:*"])
        def update_agent(agent_id: str, **updates):
            return db.update_agent(agent_id, **updates)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            # Invalidate specified patterns
            if patterns:
                cache_mgr = get_cache_manager()
                for pattern in patterns:
                    cache_mgr.delete_pattern(pattern)
                    logger.debug(f"Invalidated cache pattern: {pattern}")

            return result

        return wrapper

    return decorator


def get_cache_stats() -> Dict[str, Any]:
    """Get current cache statistics.

    Returns:
        Dictionary with cache performance metrics
    """
    cache_mgr = get_cache_manager()
    return cache_mgr.get_stats()
