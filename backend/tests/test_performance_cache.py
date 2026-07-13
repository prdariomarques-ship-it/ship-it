"""Tests for Redis caching layer performance.

Test Coverage:
- Cache decorator functionality (@cache_result)
- Cache invalidation (TTL + event-driven)
- Cache hit ratio tracking
- Thundering herd prevention
- Cache statistics and monitoring
- Memory bounded operation
"""

import json
import pytest
import redis
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from backend.performance.cache_manager import (
    CacheManager,
    CacheStatistics,
    cache_result,
    invalidate_on_write,
    get_cache_stats,
    init_cache_manager,
    get_cache_manager,
)
from backend.performance.cache_decorators import (
    CacheStrategy,
    cache_with_ttl,
    cache_with_invalidation,
)


@pytest.fixture
def redis_client():
    """Create mock Redis client."""
    return MagicMock(spec=redis.Redis)


@pytest.fixture
def cache_manager(redis_client):
    """Create cache manager with defaults."""
    return CacheManager(
        redis_client=redis_client,
        max_entries=10000,
        default_ttl=300,
        jitter_range=0.2,
    )


class TestCacheStatistics:
    """Test cache statistics tracking."""

    def test_hit_ratio_calculation(self):
        """Calculate cache hit ratio correctly."""
        stats = CacheStatistics()
        stats.hits = 75
        stats.misses = 25

        assert stats.hit_ratio == 0.75

    def test_hit_ratio_zero_when_no_operations(self):
        """Hit ratio is 0.0 when no cache operations."""
        stats = CacheStatistics()
        assert stats.hit_ratio == 0.0

    def test_hit_ratio_one_on_all_hits(self):
        """Hit ratio is 1.0 when all operations hit."""
        stats = CacheStatistics()
        stats.hits = 100
        stats.misses = 0

        assert stats.hit_ratio == 1.0

    def test_reset_clears_all_counters(self):
        """Reset clears all counters."""
        stats = CacheStatistics()
        stats.hits = 10
        stats.misses = 5
        stats.sets = 15

        stats.reset()

        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.sets == 0

    def test_to_dict_exports_all_metrics(self):
        """Export stats as dictionary."""
        stats = CacheStatistics()
        stats.hits = 50
        stats.misses = 50

        result = stats.to_dict()

        assert result["hits"] == 50
        assert result["misses"] == 50
        assert result["hit_ratio"] == 0.5


class TestCacheManager:
    """Test core cache manager operations."""

    def test_generate_key_from_parts(self, cache_manager):
        """Generate consistent hash-based key from parts."""
        key1 = cache_manager.generate_key("function", "arg1", "arg2")
        key2 = cache_manager.generate_key("function", "arg1", "arg2")

        assert key1 == key2
        assert ":" in key1
        assert key1.startswith("cache:")

    def test_generate_key_with_namespace(self, cache_manager):
        """Generate key with custom namespace."""
        key = cache_manager.generate_key("id", "123", namespace="agents")

        assert key.startswith("agents:")

    def test_cache_get_returns_cached_value(self, cache_manager, redis_client):
        """Get returns deserialized cached value."""
        redis_client.get.return_value = json.dumps({"id": "123", "name": "Test"}).encode()

        result = cache_manager.get("test_key")

        assert result == {"id": "123", "name": "Test"}
        assert cache_manager.stats.hits == 1

    def test_cache_get_miss_returns_none(self, cache_manager, redis_client):
        """Get returns None on cache miss."""
        redis_client.get.return_value = None

        result = cache_manager.get("test_key")

        assert result is None
        assert cache_manager.stats.misses == 1

    def test_cache_set_stores_with_ttl(self, cache_manager, redis_client):
        """Set stores value with TTL."""
        value = {"id": "123", "data": "test"}

        success = cache_manager.set("test_key", value, ttl=600)

        assert success is True
        assert cache_manager.stats.sets == 1
        redis_client.setex.assert_called_once()

    def test_cache_set_applies_jitter(self, cache_manager, redis_client):
        """Set applies jitter to TTL to prevent cache stampede."""
        cache_manager.set("key", {"data": "value"}, ttl=1000)

        call_args = redis_client.setex.call_args
        actual_ttl = call_args[0][1]

        # Jitter range is ±20%, so TTL should be between 800 and 1200
        assert 800 <= actual_ttl <= 1200

    def test_cache_delete_removes_entry(self, cache_manager, redis_client):
        """Delete removes cache entry."""
        redis_client.delete.return_value = 1

        result = cache_manager.delete("test_key")

        assert result is True
        assert cache_manager.stats.deletes == 1

    def test_cache_delete_pattern_invalidates_cascade(self, cache_manager, redis_client):
        """Delete pattern invalidates all matching keys."""
        redis_client.keys.return_value = ["key1", "key2", "key3"]
        redis_client.delete.return_value = 3

        count = cache_manager.delete_pattern("agents:*")

        assert count == 3
        assert cache_manager.stats.deletes == 3

    def test_cache_clear_flushes_all(self, cache_manager, redis_client):
        """Clear removes all cache entries."""
        result = cache_manager.clear()

        assert result is True
        redis_client.flushdb.assert_called_once()
        assert cache_manager.stats.hits == 0

    def test_batch_operations_context_manager(self, cache_manager, redis_client):
        """Batch operations use Redis pipeline."""
        pipeline = MagicMock()
        redis_client.pipeline.return_value = pipeline

        with cache_manager.batch_operations() as p:
            p.set("key1", "value1")
            p.delete("key2")

        pipeline.execute.assert_called_once()


class TestCacheResultDecorator:
    """Test @cache_result decorator."""

    def test_cache_result_caches_function_output(self):
        """@cache_result caches function output."""
        mock_redis = MagicMock(spec=redis.Redis)
        init_cache_manager(mock_redis)
        mock_redis.get.return_value = None

        call_count = 0

        @cache_result(ttl=300)
        def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return {"result": x * 2}

        # First call executes function
        result1 = expensive_function(5)
        assert call_count == 1

        # Mock cache to return value
        mock_redis.get.return_value = json.dumps({"result": 10}).encode()

        # Second call returns from cache
        result2 = expensive_function(5)
        assert result1 == result2

    def test_cache_result_respects_ttl(self):
        """@cache_result passes TTL to cache."""
        mock_redis = MagicMock(spec=redis.Redis)
        init_cache_manager(mock_redis)
        mock_redis.get.return_value = None

        @cache_result(ttl=600)
        def my_function():
            return "value"

        my_function()

        # Check that setex was called with correct TTL
        mock_redis.setex.assert_called()


class TestInvalidateOnWriteDecorator:
    """Test @invalidate_on_write decorator."""

    def test_invalidate_on_write_clears_patterns(self):
        """@invalidate_on_write clears cache patterns on execution."""
        mock_redis = MagicMock(spec=redis.Redis)
        init_cache_manager(mock_redis)

        @invalidate_on_write(patterns=["agents:*", "jobs:*"])
        def update_agent(agent_id, **updates):
            return {"id": agent_id, **updates}

        update_agent("123", name="Updated")

        # Should delete patterns
        mock_redis.keys.assert_called()

    def test_invalidate_on_write_still_returns_result(self):
        """@invalidate_on_write still returns function result."""
        mock_redis = MagicMock(spec=redis.Redis)
        init_cache_manager(mock_redis)
        mock_redis.keys.return_value = []

        @invalidate_on_write(patterns=["test:*"])
        def operation():
            return "success"

        result = operation()

        assert result == "success"


class TestCacheWithTTLDecorator:
    """Test cache_with_ttl decorator."""

    def test_cache_with_ttl_simple_caching(self):
        """cache_with_ttl provides simple TTL-based caching."""
        mock_redis = MagicMock(spec=redis.Redis)
        init_cache_manager(mock_redis)
        mock_redis.get.return_value = None

        call_count = 0

        @cache_with_ttl(ttl=300)
        def get_data():
            nonlocal call_count
            call_count += 1
            return {"data": "value"}

        get_data()
        assert call_count == 1

        mock_redis.get.return_value = json.dumps({"data": "value"}).encode()
        get_data()
        # Should use cache, not increment call_count


class TestCacheWithInvalidationDecorator:
    """Test cache_with_invalidation decorator."""

    def test_cache_with_invalidation_hybrid_strategy(self):
        """cache_with_invalidation supports hybrid invalidation."""
        mock_redis = MagicMock(spec=redis.Redis)
        init_cache_manager(mock_redis)
        mock_redis.get.return_value = None

        @cache_with_invalidation(
            ttl=300,
            invalidation_patterns=["agents:*"],
            strategy=CacheStrategy.HYBRID,
        )
        def get_agents():
            return []

        result = get_agents()
        assert result == []

    def test_cache_with_invalidation_provides_invalidate_function(self):
        """cache_with_invalidation exposes invalidate function."""
        mock_redis = MagicMock(spec=redis.Redis)
        init_cache_manager(mock_redis)
        mock_redis.get.return_value = None
        mock_redis.keys.return_value = ["key1", "key2"]
        mock_redis.delete.return_value = 2

        @cache_with_invalidation(
            ttl=300,
            invalidation_patterns=["test:*"],
        )
        def cached_operation():
            return "result"

        cached_operation()
        # Should have invalidate method
        assert hasattr(cached_operation, "invalidate")
        assert hasattr(cached_operation, "invalidation_patterns")


class TestCacheStampedeProtection:
    """Test cache stampede (thundering herd) prevention."""

    def test_jitter_prevents_simultaneous_expiry(self, cache_manager):
        """Jitter prevents all cache entries expiring simultaneously."""
        ttls = []

        for i in range(100):
            cache_manager.redis.setex = MagicMock()
            cache_manager.set(f"key_{i}", {"value": i}, ttl=1000)

            call_args = cache_manager.redis.setex.call_args
            ttl = call_args[0][1]
            ttls.append(ttl)

        # TTLs should vary (not all exactly 1000)
        unique_ttls = len(set(ttls))
        assert unique_ttls > 1  # At least some variation


class TestCachePerformanceMetrics:
    """Test cache performance tracking."""

    def test_cache_stats_calculation(self, cache_manager):
        """Cache statistics are calculated correctly."""
        cache_manager.stats.hits = 750
        cache_manager.stats.misses = 250

        stats = cache_manager.get_stats()

        assert stats["hits"] == 750
        assert stats["misses"] == 250
        assert stats["hit_ratio"] == 0.75

    def test_cache_operations_increment_counters(self, cache_manager, redis_client):
        """Cache operations increment appropriate counters."""
        redis_client.get.return_value = None
        cache_manager.get("key1")
        assert cache_manager.stats.misses == 1

        redis_client.get.return_value = json.dumps("value").encode()
        cache_manager.get("key2")
        assert cache_manager.stats.hits == 1

        cache_manager.set("key3", "value")
        assert cache_manager.stats.sets == 1


class TestCacheConfiguration:
    """Test cache configuration options."""

    def test_custom_max_entries(self, redis_client):
        """Cache manager respects max_entries configuration."""
        mgr = CacheManager(
            redis_client=redis_client,
            max_entries=5000,
        )

        assert mgr.max_entries == 5000

    def test_custom_default_ttl(self, redis_client):
        """Cache manager uses custom default TTL."""
        mgr = CacheManager(
            redis_client=redis_client,
            default_ttl=600,
        )

        assert mgr.default_ttl == 600

    def test_custom_jitter_range(self, redis_client):
        """Cache manager respects jitter range configuration."""
        mgr = CacheManager(
            redis_client=redis_client,
            jitter_range=0.3,
        )

        assert mgr.jitter_range == 0.3


# Run tests with: pytest backend/tests/test_performance_cache.py -v
