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
"""
from fastapi import FastAPI

from utils.logging import get_logger

logger = get_logger(__name__)

_tracing_configured = False


def setup_tracing(app: FastAPI, *, enabled: bool, otlp_endpoint: str, service_name: str) -> None:
    global _tracing_configured
    if not enabled:
        return
    if _tracing_configured:
        # Re-entrant safety: create_app() can run more than once in a test
        # session (each test module importing main fresh); instrumenting
        # the same SQLAlchemy engine/httpx client twice raises.
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

    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint) if otlp_endpoint else ConsoleSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    from database.session import engine

    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    _tracing_configured = True
    logger.info(
        "OpenTelemetry tracing enabled (service=%s, exporter=%s)",
        service_name,
        "otlp" if otlp_endpoint else "console",
    )
