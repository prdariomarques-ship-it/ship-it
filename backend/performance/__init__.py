"""Performance optimization module for Dario Platform.

This module provides:
- Query optimization (N+1 detection, eager loading)
- Redis caching layer with TTL and event-driven invalidation
- Performance monitoring and metrics
- Index recommendations and management
"""

from backend.performance.cache_manager import (
    CacheManager,
    cache_result,
    invalidate_on_write,
    get_cache_stats,
)
from backend.performance.query_optimizer import (
    QueryOptimizer,
    analyze_endpoint_queries,
    recommend_indexes,
)
from backend.performance.cache_decorators import (
    CacheStrategy,
    cache_with_ttl,
    cache_with_invalidation,
)

__all__ = [
    "CacheManager",
    "cache_result",
    "invalidate_on_write",
    "get_cache_stats",
    "QueryOptimizer",
    "analyze_endpoint_queries",
    "recommend_indexes",
    "CacheStrategy",
    "cache_with_ttl",
    "cache_with_invalidation",
]
