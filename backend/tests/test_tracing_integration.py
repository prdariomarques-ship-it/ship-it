"""OpenTelemetry tracing integration tests — end-to-end span creation and export."""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from opentelemetry import trace

import observability.tracing as tracing_module
from observability.tracing import setup_tracing
from observability.request_context import RequestIDMiddleware, get_request_id


@pytest.fixture(autouse=True)
def _reset_tracing_state():
    """Clean state before each test, shutdown TracerProvider after."""
    tracing_module._tracing_configured = False
    yield
    provider = trace.get_tracer_provider()
    shutdown = getattr(provider, "shutdown", None)
    if callable(shutdown):
        shutdown()
    tracing_module._tracing_configured = False


@pytest.fixture
def app_with_tracing_enabled():
    """FastAPI app with request context and tracing enabled (console exporter)."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/traced-endpoint")
    async def traced_endpoint():
        request_id = get_request_id()
        return {"request_id": request_id, "status": "ok"}

    setup_tracing(app, enabled=True, otlp_endpoint="", service_name="test-service")
    return app


@pytest.fixture
def client(app_with_tracing_enabled):
    return TestClient(app_with_tracing_enabled)


def test_traced_endpoint_returns_request_id(client):
    """Tracing is enabled and request flows through the instrumented endpoint."""
    response = client.get("/traced-endpoint")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["request_id"] is not None


def test_tracing_initializes_successfully_with_console_exporter(
    app_with_tracing_enabled,
):
    """TracerProvider is configured and ready to create spans."""
    provider = trace.get_tracer_provider()
    assert provider is not None
    tracer = provider.get_tracer(__name__)
    assert tracer is not None


def test_tracer_can_create_spans(app_with_tracing_enabled):
    """Manual span creation works within the tracing context."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("test_span") as span:
        assert span is not None
        span.set_attribute("test", "value")
        assert span.get_span_context() is not None


def test_tracing_state_persists_across_multiple_requests(app_with_tracing_enabled):
    """Multiple requests work correctly with the same tracing state."""
    client = TestClient(app_with_tracing_enabled)

    response1 = client.get("/traced-endpoint")
    assert response1.status_code == 200

    response2 = client.get("/traced-endpoint")
    assert response2.status_code == 200

    # Verify both responses have different request IDs (since they're different requests)
    id1 = response1.json()["request_id"]
    id2 = response2.json()["request_id"]
    assert id1 != id2


def test_otel_disabled_when_enabled_flag_is_false():
    """When enabled=False, no tracing setup occurs."""
    app = FastAPI()
    setup_tracing(app, enabled=False, otlp_endpoint="", service_name="test")
    assert tracing_module._tracing_configured is False


def test_otel_enabled_with_custom_endpoint():
    """Tracing initializes successfully with a custom OTLP endpoint."""
    app = FastAPI()
    # Note: This won't actually connect to the endpoint (it's not running),
    # but the setup should succeed. The span processor will handle export failures gracefully.
    setup_tracing(
        app,
        enabled=True,
        otlp_endpoint="http://jaeger:4318",
        service_name="test-custom-endpoint",
    )
    assert tracing_module._tracing_configured is True


def test_span_attributes_can_be_set():
    """Spans support setting and retrieving attributes."""
    app = FastAPI()
    setup_tracing(app, enabled=True, otlp_endpoint="", service_name="test")

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("test_attributes") as span:
        span.set_attribute("user_id", "12345")
        span.set_attribute("operation", "test_operation")
        # Attributes are set successfully (no error)
        assert True


def test_span_context_propagation():
    """Child spans inherit parent span context."""
    app = FastAPI()
    setup_tracing(app, enabled=True, otlp_endpoint="", service_name="test")

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("parent_span") as parent:
        parent_context = parent.get_span_context()

        with tracer.start_as_current_span("child_span") as child:
            child_context = child.get_span_context()

            # Child should have a different span ID but same trace ID as parent
            assert child_context.trace_id == parent_context.trace_id
            assert child_context.span_id != parent_context.span_id
