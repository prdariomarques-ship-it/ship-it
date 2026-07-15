"""OpenTelemetry distributed tracing — off by default, safe to leave off.

No OTel collector exists in every environment this runs in (dev, CI,
sandboxes), so tracing only activates when `OTEL_ENABLED=true` is set
explicitly. When enabled, spans export via OTLP/HTTP to
`OTEL_EXPORTER_OTLP_ENDPOINT` (any OTel-compatible backend: Jaeger, Tempo,
Honeycomp, a vendor collector, ...); with no endpoint configured it falls
back to a console exporter so `OTEL_ENABLED=true` alone is still useful for
local debugging.

Auto-instruments the three places a request's latency actually comes from:
FastAPI (one span per HTTP request), SQLAlchemy (one span per query) and
httpx (one span per outbound call — LLM providers, WhatsApp gateways, Google
APIs). No manual span creation was added anywhere else in the codebase —
those three cover the request lifecycle without touching business logic.

Includes sampling (configurable strategies), log-to-trace correlation (trace_id
in logs), Prometheus exemplars for metric-to-trace linking, and operational
metrics for tracing health monitoring.
"""
from typing import Optional

from fastapi import FastAPI

from utils.logging import get_logger

logger = get_logger(__name__)

_tracing_configured = False
_meter_provider = None


def setup_tracing(
    app: FastAPI,
    *,
    enabled: bool,
    otlp_endpoint: str,
    service_name: str,
    sampling: Optional[str] = None,
    prometheus_metrics: bool = False,
) -> None:
    """Set up OpenTelemetry tracing with sampling, metrics, and log correlation.

    Args:
        app: FastAPI application
        enabled: Enable tracing
        otlp_endpoint: OTLP/HTTP exporter endpoint
        service_name: Service name for resource
        sampling: Sampling strategy ("always", "never", "fixed:0.1", "parent-fixed:0.1", "error:0.05")
        prometheus_metrics: Enable Prometheus metrics reader
    """
    global _tracing_configured, _meter_provider
    if not enabled:
        return
    if _tracing_configured:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except ImportError:
        logger.warning("OTEL_ENABLED=true but opentelemetry packages are not installed; tracing disabled")
        return

    from observability.sampling import get_sampler_from_env
    from observability.operational_metrics import setup_operational_metrics, set_sampling_rate

    resource = Resource.create({SERVICE_NAME: service_name})

    # Initialize sampling strategy
    sampler_strategy = get_sampler_from_env(sampling)
    sampler = sampler_strategy.get_sampler()
    set_sampling_rate(sampler_strategy.get_rate())

    provider = TracerProvider(resource=resource, sampler=sampler)  # type: ignore[arg-type]
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint) if otlp_endpoint else ConsoleSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Initialize operational metrics
    _meter_provider = setup_operational_metrics(prometheus_metrics)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    from database.session import engine

    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    _tracing_configured = True
    logger.info(
        "OpenTelemetry tracing enabled (service=%s, exporter=%s, sampling=%s, metrics=%s)",
        service_name,
        "otlp" if otlp_endpoint else "console",
        sampling or "default",
        "prometheus" if prometheus_metrics else "memory",
    )
