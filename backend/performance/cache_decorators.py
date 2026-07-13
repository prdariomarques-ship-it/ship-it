"""Advanced cache decorators with flexible invalidation strategies.

Provides:
- CacheStrategy enum for different caching patterns
- cache_with_ttl: Simple TTL-based caching
- cache_with_invalidation: TTL + event-driven invalidation
- cache_warming: Preload hot data
"""

from enum import Enum
from functools import wraps
from typing import Any, Callable, List, Optional, Dict
import logging

logger = logging.getLogger(__name__)


class CacheStrategy(str, Enum):
    """Cache invalidation strategy types."""

    TTL_ONLY = "ttl_only"  # Expire after TTL
    EVENT_DRIVEN = "event_driven"  # Invalidate on mutations
    HYBRID = "hybrid"  # TTL + event-driven
    MANUAL = "manual"  # Explicit invalidation only


def cache_with_ttl(
    ttl: int,
    namespace: str = "cache",
) -> Callable:
    """Decorator for simple TTL-based caching.

    Args:
        ttl: Time-to-live in seconds
        namespace: Cache namespace

    Example:
        @cache_with_ttl(ttl=300, namespace="agents")
        def get_all_agents():
            return fetch_agents_from_db()
    """
    from backend.performance.cache_manager import get_cache_manager

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_mgr = get_cache_manager()
            key = cache_mgr.generate_key(func.__name__, namespace=namespace)

            # Check cache
            cached = cache_mgr.get(key)
            if cached is not None:
                return cached

            # Execute and cache
            result = func(*args, **kwargs)
            if result is not None:
                cache_mgr.set(key, result, ttl=ttl)

            return result

        return wrapper

    return decorator


def cache_with_invalidation(
    ttl: int,
    invalidation_patterns: List[str],
    namespace: str = "cache",
    strategy: CacheStrategy = CacheStrategy.HYBRID,
) -> Callable:
    """Decorator with flexible invalidation strategy.

    Args:
        ttl: Time-to-live in seconds
        invalidation_patterns: Patterns to invalidate on write (e.g., ["agents:*"])
        namespace: Cache namespace
        strategy: Invalidation strategy (TTL_ONLY, EVENT_DRIVEN, HYBRID, MANUAL)

    Example:
        @cache_with_invalidation(
            ttl=300,
            invalidation_patterns=["agents:*"],
            strategy=CacheStrategy.HYBRID
        )
        def get_agents_by_status(status: str):
            return fetch_agents_by_status(status)
    """
    from backend.performance.cache_manager import get_cache_manager

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_mgr = get_cache_manager()

            # Generate key with arguments
            key_parts = (func.__name__, *args, *sorted(kwargs.items()))
            key = cache_mgr.generate_key(*key_parts, namespace=namespace)

            # Check cache if strategy allows
            if strategy in (CacheStrategy.TTL_ONLY, CacheStrategy.HYBRID):
                cached = cache_mgr.get(key)
                if cached is not None:
                    return cached

            # Execute function
            result = func(*args, **kwargs)

            # Cache result if strategy allows
            if strategy != CacheStrategy.MANUAL:
                if result is not None:
                    cache_mgr.set(key, result, ttl=ttl)

            return result

        # Add invalidation function to wrapper
        def invalidate(*patterns: str) -> int:
            """Invalidate cache patterns for this function."""
            cache_mgr = get_cache_manager()
            deleted = 0
            for pattern in (patterns or invalidation_patterns):
                deleted += cache_mgr.delete_pattern(pattern)
            logger.debug(f"Invalidated {deleted} cache entries for {func.__name__}")
            return deleted

        wrapper.invalidate = invalidate
        wrapper.invalidation_patterns = invalidation_patterns

        return wrapper

    return decorator


def cache_warming(
    cache_keys: List[str],
    data_loader: Callable[[], Dict[str, Any]],
    ttl: int = 3600,
) -> None:
    """Preload hot data into cache at startup.

    Args:
        cache_keys: List of cache keys to warm
        data_loader: Function that returns dict of {key: value} pairs
        ttl: Time-to-live for cached entries

    Example:
        def load_hot_data():
            return {
                "agents:all": fetch_all_agents(),
                "status:active": fetch_active_count(),
            }

        cache_warming(
            cache_keys=["agents:all", "status:active"],
            data_loader=load_hot_data,
            ttl=3600
        )
    """
    try:
        from backend.performance.cache_manager import get_cache_manager

        cache_mgr = get_cache_manager()
        data = data_loader()

        for key in cache_keys:
            if key in data:
                cache_mgr.set(key, data[key], ttl=ttl)
                logger.info(f"Warmed cache key: {key}")
    except Exception as e:
        logger.warning(f"Cache warming failed: {e}")


class CacheableMixin:
    """Mixin for models to provide caching support.

    Usage:
        class Agent(Base, CacheableMixin):
            id: str
            name: str

        agent = Agent(id="123", name="Test")
        cached = agent.cache()  # Returns self
        retrieved = Agent.get_cached(id="123")
    """

    cache_ttl = 300  # Override in subclass

    @classmethod
    def get_cached(cls, **filters) -> Optional[Any]:
        """Get model instance from cache or database.

        Args:
            **filters: Filter parameters (e.g., id="123")

        Returns:
            Model instance or None
        """
        from backend.performance.cache_manager import get_cache_manager

        cache_mgr = get_cache_manager()
        key = cache_mgr.generate_key(cls.__name__, *sorted(filters.items()))

        # Try cache
        cached = cache_mgr.get(key)
        if cached is not None:
            return cached

        # Query database (implementation depends on ORM)
        # This is a template - actual query depends on database module
        return None

    def cache(self, ttl: Optional[int] = None) -> "CacheableMixin":
        """Cache this model instance.

        Args:
            ttl: Time-to-live (None = use class default)

        Returns:
            Self for chaining
        """
        from backend.performance.cache_manager import get_cache_manager

        cache_mgr = get_cache_manager()
        key = cache_mgr.generate_key(self.__class__.__name__, str(self.id))
        cache_mgr.set(key, self, ttl=ttl or self.cache_ttl)
        return self

    @classmethod
    def clear_cache(cls, **filters) -> bool:
        """Clear cache for instances matching filters.

        Args:
            **filters: Filter parameters

        Returns:
            True if cleared successfully
        """
        from backend.performance.cache_manager import get_cache_manager

        cache_mgr = get_cache_manager()
        if filters:
            pattern = f"{cls.__name__}:*"
            cache_mgr.delete_pattern(pattern)
        else:
            cache_mgr.clear()
        return True
