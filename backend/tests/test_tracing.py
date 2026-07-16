"""OpenTelemetry setup: safe no-op when disabled, and initializes without
error when enabled (both with and without an OTLP endpoint configured)."""

import pytest
from fastapi import FastAPI
from opentelemetry import trace

import observability.tracing as tracing_module
from observability.tracing import setup_tracing


def _fresh_app() -> FastAPI:
    return FastAPI()


@pytest.fixture(autouse=True)
def _reset_tracing_state():
    """Each test gets a clean `_tracing_configured` flag, and the global
    TracerProvider (a real background export thread once initialized) is
    shut down afterwards so it doesn't outlive the test process and try to
    write to stdout after pytest has closed it."""
    tracing_module._tracing_configured = False
    yield
    provider = trace.get_tracer_provider()
    shutdown = getattr(provider, "shutdown", None)
    if callable(shutdown):
        shutdown()
    tracing_module._tracing_configured = False


def test_setup_tracing_is_a_noop_when_disabled():
    app = _fresh_app()
    setup_tracing(app, enabled=False, otlp_endpoint="", service_name="test")
    assert tracing_module._tracing_configured is False


def test_setup_tracing_initializes_with_console_exporter_when_no_endpoint():
    app = _fresh_app()
    setup_tracing(app, enabled=True, otlp_endpoint="", service_name="test-console")
    assert tracing_module._tracing_configured is True


def test_setup_tracing_is_idempotent():
    """A second call (e.g. a second create_app() in the same process during
    tests) must not raise from double-instrumenting the same engine/client."""
    app = _fresh_app()
    setup_tracing(app, enabled=True, otlp_endpoint="", service_name="test-idempotent")
    assert tracing_module._tracing_configured is True
    # Second call: should return early without attempting to instrument again.
    setup_tracing(app, enabled=True, otlp_endpoint="", service_name="test-idempotent")
