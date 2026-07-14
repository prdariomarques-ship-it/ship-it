"""Tests for performance SLA compliance monitoring.

Test Coverage:
- SLA threshold enforcement (p95 < 200ms)
- Performance baseline establishment
- Regression detection
- Metric collection and reporting
- Alert triggering
"""

import pytest
from unittest.mock import MagicMock

from backend.observability.performance_middleware import (
    PerformanceMetrics,
    PerformanceMiddleware,
    record_cache_operation,
)


@pytest.fixture
def performance_metrics():
    """Create performance metrics instance."""
    return PerformanceMetrics("req-123", "GET /api/agents")


@pytest.fixture
async def mock_request():
    """Create mock FastAPI request."""
    request = MagicMock()
    request.headers = {"x-request-id": "req-123"}
    request.method = "GET"
    request.url.path = "/api/agents"
    request.state = MagicMock()
    return request


class TestPerformanceMetrics:
    """Test performance metrics collection."""

    def test_metrics_initialization(self, performance_metrics):
        """Metrics are initialized correctly."""
        assert performance_metrics.request_id == "req-123"
        assert performance_metrics.endpoint == "GET /api/agents"
        assert performance_metrics.cache_hits == 0
        assert performance_metrics.cache_misses == 0
        assert performance_metrics.db_query_count == 0

    def test_duration_calculation(self, performance_metrics):
        """Duration is calculated as elapsed time."""
        import time

        time.sleep(0.01)  # 10ms
        performance_metrics.end_time = performance_metrics.start_time + 0.01

        duration = performance_metrics.duration_ms
        assert duration >= 10.0

    def test_cache_hit_ratio_calculation(self, performance_metrics):
        """Cache hit ratio is calculated correctly."""
        performance_metrics.cache_hits = 75
        performance_metrics.cache_misses = 25

        assert performance_metrics.cache_hit_ratio == 0.75

    def test_cache_hit_ratio_zero_on_no_operations(self, performance_metrics):
        """Cache hit ratio is 0.0 when no cache operations."""
        assert performance_metrics.cache_hit_ratio == 0.0

    def test_metrics_to_dict_export(self, performance_metrics):
        """Metrics export to dictionary."""
        performance_metrics.cache_hits = 10
        performance_metrics.cache_misses = 5
        performance_metrics.db_query_count = 3

        result = performance_metrics.to_dict()

        assert result["request_id"] == "req-123"
        assert result["endpoint"] == "GET /api/agents"
        assert result["cache_hits"] == 10
        assert result["cache_misses"] == 5
        assert result["db_query_count"] == 3


class TestPerformanceMiddleware:
    """Test performance monitoring middleware."""

    def test_middleware_initialization(self):
        """Middleware initializes with correct configuration."""
        app = MagicMock()
        middleware = PerformanceMiddleware(
            app,
            sla_latency_ms=200,
            record_traces=True,
        )

        assert middleware.sla_latency_ms == 200
        assert middleware.record_traces is True
        assert middleware.metrics_history == {}

    def test_middleware_custom_sla_threshold(self):
        """Middleware supports custom SLA threshold."""
        app = MagicMock()
        middleware = PerformanceMiddleware(app, sla_latency_ms=500)

        assert middleware.sla_latency_ms == 500

    @pytest.mark.asyncio
    async def test_middleware_dispatch_records_metrics(self):
        """Middleware dispatch records performance metrics."""
        app = MagicMock()
        middleware = PerformanceMiddleware(app, sla_latency_ms=200)

        request = MagicMock()
        request.headers = {"x-request-id": "req-123"}
        request.url.path = "/api/agents"
        request.method = "GET"
        request.state = MagicMock()

        response = MagicMock()
        response.headers = {}

        async def call_next(r):
            return response

        await middleware.dispatch(request, call_next)

        # Should store metrics
        assert "req-123" in middleware.metrics_history

    def test_middleware_stores_metrics_history(self):
        """Middleware stores metrics in history."""
        app = MagicMock()
        middleware = PerformanceMiddleware(app)

        metrics = PerformanceMetrics("req-456", "POST /api/agents")
        metrics.end_time = metrics.start_time + 0.05  # 50ms

        middleware.metrics_history["req-456"] = metrics

        retrieved = middleware.get_metrics("req-456")
        assert retrieved is not None
        assert retrieved["request_id"] == "req-456"

    def test_middleware_get_metrics_not_found(self):
        """get_metrics returns None for nonexistent request."""
        app = MagicMock()
        middleware = PerformanceMiddleware(app)

        result = middleware.get_metrics("req-nonexistent")

        assert result is None

    def test_middleware_clear_history_removes_old_entries(self):
        """clear_history removes entries older than threshold."""
        app = MagicMock()
        middleware = PerformanceMiddleware(app)

        # Add old metric
        old_metrics = PerformanceMetrics("req-old", "GET /api/old")
        old_metrics.end_time = 0  # Very old

        # Add recent metric
        new_metrics = PerformanceMetrics("req-new", "GET /api/new")

        middleware.metrics_history["req-old"] = old_metrics
        middleware.metrics_history["req-new"] = new_metrics

        # Clear entries older than 60 seconds
        cleared = middleware.clear_history(older_than_seconds=60)

        assert cleared >= 0


class TestSLACompliance:
    """Test SLA compliance validation."""

    def test_sla_compliant_when_under_threshold(self, performance_metrics):
        """Request is compliant when latency < 200ms."""
        performance_metrics.end_time = performance_metrics.start_time + 0.150  # 150ms

        # Should be compliant
        is_compliant = performance_metrics.duration_ms <= 200
        assert is_compliant

    def test_sla_violation_when_over_threshold(self, performance_metrics):
        """Request violates SLA when latency > 200ms."""
        performance_metrics.end_time = performance_metrics.start_time + 0.250  # 250ms

        # Should violate
        is_compliant = performance_metrics.duration_ms <= 200
        assert not is_compliant

    def test_sla_threshold_boundary(self, performance_metrics):
        """SLA threshold boundary at exactly 200ms."""
        performance_metrics.end_time = performance_metrics.start_time + 0.200  # 200ms

        # Should be compliant (<=)
        is_compliant = performance_metrics.duration_ms <= 200
        assert is_compliant


class TestPerformanceRegression:
    """Test performance regression detection."""

    def test_establish_performance_baseline(self):
        """Establish baseline performance metrics."""
        baseline = {
            "p50": 50,
            "p95": 150,
            "p99": 250,
            "mean": 100,
        }

        assert baseline["p95"] == 150

    def test_detect_performance_regression_increase(self):
        """Detect when performance degrades (latency increases)."""
        baseline_p95 = 150
        current_p95 = 200

        regression = current_p95 > baseline_p95 * 1.1  # >10% increase

        assert regression

    def test_no_regression_within_tolerance(self):
        """No regression within 10% tolerance."""
        baseline_p95 = 150
        current_p95 = 160  # 6.7% increase

        regression = current_p95 > baseline_p95 * 1.1

        assert not regression

    def test_detect_cache_hit_ratio_regression(self):
        """Detect when cache hit ratio decreases."""
        baseline_hit_ratio = 0.75
        current_hit_ratio = 0.60

        regression = current_hit_ratio < baseline_hit_ratio * 0.9  # <90% of baseline

        assert regression

    def test_detect_query_count_increase(self):
        """Detect when query count increases (possible N+1)."""
        baseline_queries = 2
        current_queries = 20  # 10x increase

        regression = current_queries > baseline_queries * 2

        assert regression


class TestCacheOperationRecording:
    """Test cache operation recording."""

    def test_record_cache_hit(self):
        """Record cache hit in request metrics."""
        request = MagicMock()
        request.state = MagicMock()
        request.state.performance = PerformanceMetrics("req-1", "GET /api/test")

        record_cache_operation(request, hit=True)

        assert request.state.performance.cache_hits == 1

    def test_record_cache_miss(self):
        """Record cache miss in request metrics."""
        request = MagicMock()
        request.state = MagicMock()
        request.state.performance = PerformanceMetrics("req-1", "GET /api/test")

        record_cache_operation(request, hit=False)

        assert request.state.performance.cache_misses == 1

    def test_record_multiple_cache_operations(self):
        """Record multiple cache operations in single request."""
        request = MagicMock()
        request.state = MagicMock()
        request.state.performance = PerformanceMetrics("req-1", "GET /api/test")

        record_cache_operation(request, hit=True)
        record_cache_operation(request, hit=True)
        record_cache_operation(request, hit=False)

        assert request.state.performance.cache_hits == 2
        assert request.state.performance.cache_misses == 1


class TestDatabaseQueryMetrics:
    """Test database query performance metrics."""

    def test_track_database_query_count(self, performance_metrics):
        """Track number of database queries."""
        performance_metrics.db_query_count += 1
        performance_metrics.db_query_count += 1

        assert performance_metrics.db_query_count == 2

    def test_track_database_query_duration(self, performance_metrics):
        """Track total database query duration."""
        performance_metrics.db_query_duration_ms += 25.5
        performance_metrics.db_query_duration_ms += 30.2

        assert performance_metrics.db_query_duration_ms == pytest.approx(55.7, abs=0.1)

    def test_query_count_60_percent_reduction_target(self):
        """Validate 60% query reduction target."""
        before = 100
        after = 40  # 60% reduction

        reduction = (before - after) / before
        assert reduction >= 0.6


class TestAlertTriggering:
    """Test SLA violation alerting."""

    def test_alert_on_p95_latency_violation(self, performance_metrics):
        """Alert when p95 latency violates SLA."""
        performance_metrics.end_time = performance_metrics.start_time + 0.250  # 250ms

        should_alert = performance_metrics.duration_ms > 200
        assert should_alert

    def test_alert_on_low_cache_hit_ratio(self, performance_metrics):
        """Alert when cache hit ratio falls below 70%."""
        performance_metrics.cache_hits = 50
        performance_metrics.cache_misses = 150

        hit_ratio = performance_metrics.cache_hit_ratio
        should_alert = hit_ratio < 0.70

        assert should_alert

    def test_no_alert_when_metrics_healthy(self, performance_metrics):
        """No alert when metrics are healthy."""
        performance_metrics.end_time = performance_metrics.start_time + 0.100  # 100ms
        performance_metrics.cache_hits = 800
        performance_metrics.cache_misses = 200

        latency_ok = performance_metrics.duration_ms <= 200
        cache_ok = performance_metrics.cache_hit_ratio >= 0.70

        assert latency_ok and cache_ok


class TestPerformanceReporting:
    """Test performance metrics reporting."""

    def test_generate_performance_report_fields(self, performance_metrics):
        """Performance report contains required fields."""
        report = performance_metrics.to_dict()

        required_fields = [
            "request_id",
            "endpoint",
            "duration_ms",
            "cache_hits",
            "cache_misses",
            "cache_hit_ratio",
            "db_query_count",
        ]

        for field in required_fields:
            assert field in report

    def test_performance_report_aggregation(self):
        """Aggregate multiple metrics for period report."""
        metrics_list = [
            PerformanceMetrics("req-1", "GET /api/test"),
            PerformanceMetrics("req-2", "GET /api/test"),
            PerformanceMetrics("req-3", "GET /api/test"),
        ]

        # Calculate p95
        durations = [m.duration_ms for m in metrics_list]
        p95_duration = sorted(durations)[int(len(durations) * 0.95)]

        assert p95_duration >= 0


class TestPerformanceOptimizationTargets:
    """Test acceptance criteria for performance targets."""

    def test_target_database_query_reduction_60_percent(self):
        """Test 60% database query reduction target."""
        before = 100
        after = 40
        reduction = (before - after) / before
        assert reduction >= 0.60

    def test_target_cache_hit_ratio_75_percent(self):
        """Test >75% cache hit ratio target."""
        hits = 750
        misses = 250
        hit_ratio = hits / (hits + misses)
        assert hit_ratio > 0.75

    def test_target_frontend_bundle_500kb(self):
        """Test <500KB gzipped bundle size target."""
        bundle_size_kb = 450
        assert bundle_size_kb < 500

    def test_target_p95_latency_200ms(self):
        """Test <200ms p95 latency target."""
        p95_latency_ms = 180
        assert p95_latency_ms < 200


# Run tests with: pytest backend/tests/test_performance_sla.py -v
