"""Prometheus metrics: HTTP, agent runs, job execution and WhatsApp providers."""
import time

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

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

AGENT_RUNS = Counter(
    "darioos_agent_runs_total",
    "Total agent runs via the AI Orchestrator",
    labelnames=("agent", "provider", "status"),
)

AGENT_RUN_DURATION = Histogram(
    "darioos_agent_run_duration_seconds",
    "Agent run duration in seconds (plan + tool calls + final answer)",
    labelnames=("agent",),
)

AGENT_TOOL_CALLS = Counter(
    "darioos_agent_tool_calls_total",
    "Tool calls executed by agents",
    labelnames=("tool",),
)

AGENT_TOKENS = Counter(
    "darioos_agent_tokens_total",
    "LLM tokens consumed by agent runs",
    labelnames=("provider", "kind"),  # kind: prompt | completion
)

AGENT_COST_USD = Counter(
    "darioos_agent_cost_usd_total",
    "Estimated LLM cost in USD (see providers.llm.base pricing table)",
    labelnames=("provider",),
)

JOB_DURATION = Histogram(
    "darioos_job_duration_seconds",
    "Job execution duration in seconds, per job name",
    labelnames=("name",),
)

WHATSAPP_PROVIDER_REQUESTS = Counter(
    "darioos_whatsapp_provider_requests_total",
    "Outbound HTTP calls made to a WhatsApp provider gateway",
    labelnames=("provider", "status"),  # status: ok | error
)

WHATSAPP_SESSION_STATUS = Gauge(
    "darioos_whatsapp_session_status",
    "Last known connection status of a WhatsApp provider's session "
    "(1=connected, 0=disconnected/auth_expired/reconnecting/unknown)",
    labelnames=("provider",),
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


def record_agent_run(
    *,
    agent: str,
    provider: str,
    status: str,
    duration_seconds: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
) -> None:
    AGENT_RUNS.labels(agent, provider, status).inc()
    AGENT_RUN_DURATION.labels(agent).observe(duration_seconds)
    if prompt_tokens:
        AGENT_TOKENS.labels(provider, "prompt").inc(prompt_tokens)
    if completion_tokens:
        AGENT_TOKENS.labels(provider, "completion").inc(completion_tokens)
    if cost_usd:
        AGENT_COST_USD.labels(provider).inc(cost_usd)


def record_tool_call(tool_name: str) -> None:
    AGENT_TOOL_CALLS.labels(tool_name).inc()


def record_job_duration(name: str, duration_seconds: float) -> None:
    JOB_DURATION.labels(name).observe(duration_seconds)


def record_whatsapp_request(provider: str, status: str) -> None:
    WHATSAPP_PROVIDER_REQUESTS.labels(provider, status).inc()


def record_whatsapp_session_status(provider: str, connected: bool) -> None:
    WHATSAPP_SESSION_STATUS.labels(provider).set(1 if connected else 0)
