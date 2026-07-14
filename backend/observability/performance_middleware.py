"""Performance monitoring middleware integrating with OBS-002 tracing.

Records:
- Cache hits/misses per request
- Database query duration
- Endpoint latency (p50, p95, p99)
- SLA compliance (p95 < 200ms threshold)
"""

import logging
import time
from typing import Callable, Any, Dict
from contextlib import asynccontextmanager

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """Collects performance metrics for a request."""

    def __init__(self, request_id: str, endpoint: str):
        self.request_id = request_id
        self.endpoint = endpoint
        self.start_time = time.perf_counter()
        self.cache_hits = 0
        self.cache_misses = 0
        self.db_query_count = 0
        self.db_query_duration_ms = 0.0
        self.end_time = None

    @property
    def duration_ms(self) -> float:
        """Total request duration in milliseconds."""
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return (time.perf_counter() - self.start_time) * 1000

    @property
    def cache_hit_ratio(self) -> float:
        """Cache hit ratio for this request."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total

    def to_dict(self) -> Dict[str, Any]:
        """Export metrics as dictionary."""
        return {
            "request_id": self.request_id,
            "endpoint": self.endpoint,
            "duration_ms": self.duration_ms,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_ratio": self.cache_hit_ratio,
            "db_query_count": self.db_query_count,
            "db_query_duration_ms": self.db_query_duration_ms,
        }


class PerformanceMiddleware(BaseHTTPMiddleware):
    """ASGI middleware for performance monitoring.

    Measures:
    - Request latency
    - Cache efficiency
    - Database query metrics
    - SLA compliance

    Integrates with OBS-002 tracing to record spans.
    """

    def __init__(
        self,
        app: ASGIApp,
        sla_latency_ms: int = 200,
        record_traces: bool = True,
    ):
        super().__init__(app)
        self.sla_latency_ms = sla_latency_ms
        self.record_traces = record_traces
        self.metrics_history: Dict[str, PerformanceMetrics] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and record performance metrics.

        Args:
            request: HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response with metrics recorded
        """
        # Get or create request ID from OBS-002
        request_id = request.headers.get("x-request-id", "unknown")
        endpoint = f"{request.method} {request.url.path}"

        # Create metrics object
        metrics = PerformanceMetrics(request_id, endpoint)

        # Attach metrics to request state for handlers to update
        request.state.performance = metrics

        # Process request
        time.perf_counter()
        response = await call_next(request)
        metrics.end_time = time.perf_counter()

        # Check SLA compliance
        sla_compliant = metrics.duration_ms <= self.sla_latency_ms
        status = "OK" if sla_compliant else "SLA_VIOLATION"

        # Log performance metrics
        logger.info(
            f"[PERF] {endpoint} | "
            f"latency={metrics.duration_ms:.1f}ms | "
            f"sla={status} | "
            f"cache_hits={metrics.cache_hits} | "
            f"db_queries={metrics.db_query_count}",
            extra={"metrics": metrics.to_dict()},
        )

        # Record OBS-002 tracing span if enabled
        if self.record_traces:
            self._record_trace_span(metrics, request_id, sla_compliant)

        # Add performance headers to response
        response.headers["X-Response-Time-Ms"] = str(int(metrics.duration_ms))
        response.headers["X-SLA-Status"] = status

        # Store in history for analysis
        self.metrics_history[request_id] = metrics

        return response

    def _record_trace_span(
        self,
        metrics: PerformanceMetrics,
        request_id: str,
        sla_compliant: bool,
    ) -> None:
        """Record performance metrics as OBS-002 tracing span.

        Args:
            metrics: Performance metrics for request
            request_id: Request ID from OBS-002
            sla_compliant: Whether request met SLA
        """
        try:
            from opentelemetry import trace, metrics as otel_metrics
            from observability.request_context import get_trace_id

            tracer = trace.get_tracer(__name__)
            meter = otel_metrics.get_meter(__name__)

            # Record latency metric
            latency_histogram = meter.create_histogram(
                "api_response_time_ms",
                description="API response time in milliseconds",
            )
            latency_histogram.record(metrics.duration_ms)

            # Record cache efficiency
            cache_metric = meter.create_gauge(
                "cache_hit_ratio",
                description="Cache hit ratio for request",
            )
            cache_metric.observe(metrics.cache_hit_ratio)

            # Record as tracing span
            with tracer.start_as_current_span(
                f"performance_metrics:{metrics.endpoint}"
            ) as span:
                span.set_attribute("endpoint", metrics.endpoint)
                span.set_attribute("duration_ms", metrics.duration_ms)
                span.set_attribute("cache_hits", metrics.cache_hits)
                span.set_attribute("cache_misses", metrics.cache_misses)
                span.set_attribute("db_query_count", metrics.db_query_count)
                span.set_attribute("sla_compliant", sla_compliant)
                span.set_attribute("trace_id", get_trace_id() or "unknown")

        except Exception as e:
            logger.debug(f"Failed to record performance trace: {e}")

    def get_metrics(self, request_id: str) -> Dict[str, Any]:
        """Get performance metrics for a request.

        Args:
            request_id: Request ID

        Returns:
            Metrics dictionary or None if not found
        """
        if request_id in self.metrics_history:
            return self.metrics_history[request_id].to_dict()
        return None

    def clear_history(self, older_than_seconds: int = 3600) -> int:
        """Clear old metrics from history.

        Args:
            older_than_seconds: Clear metrics older than this duration

        Returns:
            Number of entries cleared
        """
        cutoff = time.perf_counter() - older_than_seconds
        to_delete = []

        for req_id, metrics in self.metrics_history.items():
            if metrics.end_time and metrics.end_time < cutoff:
                to_delete.append(req_id)

        for req_id in to_delete:
            del self.metrics_history[req_id]

        return len(to_delete)


@asynccontextmanager
async def measure_operation(
    operation_name: str,
    request: Request,
) -> Any:
    """Context manager to measure operation duration within request.

    Args:
        operation_name: Name of operation being measured
        request: HTTP request with performance metrics

    Example:
        async with measure_operation("database_query", request):
            result = await db.query(...)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = (time.perf_counter() - start) * 1000
        if hasattr(request.state, "performance"):
            metrics = request.state.performance
            if "database" in operation_name.lower():
                metrics.db_query_duration_ms += duration
                metrics.db_query_count += 1
        logger.debug(f"[PERF_OP] {operation_name}: {duration:.1f}ms")


def record_cache_operation(
    request: Request,
    hit: bool,
) -> None:
    """Record cache hit/miss for current request.

    Args:
        request: HTTP request
        hit: True if cache hit, False if miss
    """
    if hasattr(request.state, "performance"):
        metrics = request.state.performance
        if hit:
            metrics.cache_hits += 1
        else:
            metrics.cache_misses += 1
