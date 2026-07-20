"""Prometheus metrics: HTTP, agent runs, job execution and WhatsApp providers."""

import time

from fastapi import APIRouter, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

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
    labelnames=("tool", "status"),  # status: ok | error
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

JOB_TIMEOUTS = Counter(
    "darioos_job_timeouts_total",
    "Jobs that hit jobs_execution_timeout_seconds (the global per-job "
    "execution ceiling), per job name — distinct from any other handler "
    "failure; previously only visible by grepping the persisted job log "
    "for 'execution limit' (see jobs/worker.py)",
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

GOOGLE_PROVIDER_REQUESTS = Counter(
    "darioos_google_provider_requests_total",
    "Outbound HTTP calls made to a Google API (gmail/google_calendar/"
    "google_contacts/google_drive)",
    labelnames=("provider", "status"),  # status: ok | error
)

PIPELINE_STAGE_DURATION = Histogram(
    "darioos_pipeline_stage_duration_seconds",
    "Duration of each Cognitive Pipeline stage",
    labelnames=("stage",),
)

PIPELINE_RUN_DURATION = Histogram(
    "darioos_pipeline_run_duration_seconds",
    "Total duration of one Cognitive Pipeline run, end to end",
)

INTENT_CLASSIFICATIONS = Counter(
    "darioos_intent_classifications_total",
    "Messages classified by top intent",
    labelnames=("intent",),
)

PRIORITY_CLASSIFICATIONS = Counter(
    "darioos_priority_classifications_total",
    "Messages classified by priority level",
    labelnames=("priority",),
)

PIPELINE_VALIDATION_RETRIES = Counter(
    "darioos_pipeline_validation_retries_total",
    "Response validation retries triggered by the Cognitive Pipeline",
)

PIPELINE_MEMORY_LOOKUPS = Counter(
    "darioos_pipeline_memory_lookups_total",
    "Memory/knowledge lookups performed by the Cognitive Pipeline",
    labelnames=("kind",),  # short_term | long_term | knowledge | preferences | summary
)

OBSERVATION_RUNS = Counter(
    "darioos_observation_runs_total",
    "CurrentContext snapshots built by the Context Observation Engine",
    labelnames=("trigger",),  # scheduler | event | startup
)

OBSERVATION_DURATION = Histogram(
    "darioos_observation_duration_seconds",
    "Duration of one Context Observation Engine snapshot build",
)

OBSERVATION_SOURCE_ERRORS = Counter(
    "darioos_observation_source_errors_total",
    "Best-effort observation sources skipped (dependency unavailable) while building CurrentContext",
    labelnames=("source",),
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


def record_tool_call(tool_name: str, status: str = "ok") -> None:
    AGENT_TOOL_CALLS.labels(tool_name, status).inc()


def record_job_duration(name: str, duration_seconds: float) -> None:
    JOB_DURATION.labels(name).observe(duration_seconds)


def record_job_timeout(name: str) -> None:
    JOB_TIMEOUTS.labels(name).inc()


def record_whatsapp_request(provider: str, status: str) -> None:
    WHATSAPP_PROVIDER_REQUESTS.labels(provider, status).inc()


def record_whatsapp_session_status(provider: str, connected: bool) -> None:
    WHATSAPP_SESSION_STATUS.labels(provider).set(1 if connected else 0)


def record_google_request(provider: str, status: str) -> None:
    GOOGLE_PROVIDER_REQUESTS.labels(provider, status).inc()


def record_pipeline_stage(stage: str, duration_seconds: float) -> None:
    PIPELINE_STAGE_DURATION.labels(stage).observe(duration_seconds)


def record_pipeline_run(duration_seconds: float) -> None:
    PIPELINE_RUN_DURATION.observe(duration_seconds)


def record_intent_classification(intent: str) -> None:
    INTENT_CLASSIFICATIONS.labels(intent).inc()


def record_priority_classification(priority: str) -> None:
    PRIORITY_CLASSIFICATIONS.labels(priority).inc()


def record_validation_retry() -> None:
    PIPELINE_VALIDATION_RETRIES.inc()


def record_memory_lookup(kind: str) -> None:
    PIPELINE_MEMORY_LOOKUPS.labels(kind).inc()


def record_observation_run(trigger: str, duration_seconds: float) -> None:
    OBSERVATION_RUNS.labels(trigger).inc()
    OBSERVATION_DURATION.observe(duration_seconds)


def record_observation_source_error(source: str) -> None:
    OBSERVATION_SOURCE_ERRORS.labels(source).inc()
