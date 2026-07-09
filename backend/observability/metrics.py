"""Prometheus metrics: HTTP counters/latency histogram and a /metrics endpoint."""
import time

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "darioos_http_requests_total",
    "Total HTTP requests",
    labelnames=("method", "path", "status"),
)

HTTP_DURATION = Histogram(
    "darioos_http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=("method", "path"),
)

metrics_router = APIRouter(tags=["observability"])


@metrics_router.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def metrics_middleware(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started

    # Use the route template (e.g. /api/tasks/{item_id}) to keep cardinality low.
    route = request.scope.get("route")
    path = getattr(route, "path", None) or "unmatched"

    HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    HTTP_DURATION.labels(request.method, path).observe(elapsed)
    return response
