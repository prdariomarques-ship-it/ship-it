"""W3C Trace Context standard (RFC 9110) implementation — traceparent header extraction."""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from uuid import uuid4

from middleware.trace_context import (
    TraceContextMiddleware,
    get_trace_context,
    parse_traceparent,
)
from observability.request_context import (
    RequestIDMiddleware,
    get_request_id,
    get_trace_id,
)


@pytest.fixture
def app_with_trace_context():
    """FastAPI app with trace context middleware."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TraceContextMiddleware)

    @app.get("/test")
    async def test_route():
        return {
            "request_id": get_request_id(),
            "trace_id": get_trace_id(),
            "trace_context": get_trace_context(),
        }

    return app


@pytest.fixture
def client(app_with_trace_context):
    return TestClient(app_with_trace_context)


def test_parse_traceparent_valid():
    """Parse a valid W3C traceparent header."""
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    result = parse_traceparent(traceparent)
    assert result is not None
    assert result["version"] == "00"
    assert result["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert result["span_id"] == "00f067aa0ba902b7"
    assert result["trace_flags"] == "01"


def test_parse_traceparent_invalid_length():
    """Invalid traceparent with wrong number of parts."""
    assert parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736") is None
    assert parse_traceparent("") is None


def test_parse_traceparent_invalid_format():
    """Invalid traceparent with wrong hex string lengths."""
    # version too long
    assert (
        parse_traceparent("000-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        is None
    )
    # trace_id too short
    assert (
        parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e47-00f067aa0ba902b7-01")
        is None
    )


def test_trace_context_extracted_from_header(client):
    """When traceparent header is present, it's extracted and stored in context."""
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    response = client.get("/test", headers={"traceparent": traceparent})
    assert response.status_code == 200
    data = response.json()
    # Trace context should be extracted
    assert data["trace_context"] is not None
    assert data["trace_context"]["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert data["trace_context"]["span_id"] == "00f067aa0ba902b7"
    assert data["trace_context"]["trace_flags"] == "01"


def test_trace_context_generated_from_request_id(client):
    """When no traceparent header, trace_id is generated from request_id."""
    response = client.get("/test")
    assert response.status_code == 200
    data = response.json()
    # Request ID should be generated
    assert data["request_id"] is not None
    # Trace ID should be generated from request ID (32 hex chars)
    assert data["trace_id"] is not None
    assert len(data["trace_id"]) == 32
    # Trace context from header should be None (no traceparent in request)
    assert data["trace_context"] is None


def test_trace_id_is_uuid_hex_format(client):
    """Trace ID is 32-character hex string (UUID without dashes)."""
    response = client.get("/test")
    assert response.status_code == 200
    data = response.json()
    trace_id = data["trace_id"]
    assert len(trace_id) == 32
    assert all(c in "0123456789abcdef" for c in trace_id)


def test_trace_context_with_invalid_traceparent_ignored(client):
    """Invalid traceparent header is safely ignored."""
    # Invalid traceparent (wrong format)
    response = client.get("/test", headers={"traceparent": "invalid"})
    assert response.status_code == 200
    data = response.json()
    # Should still generate request_id and trace_id
    assert data["request_id"] is not None
    assert data["trace_id"] is not None
    # But trace_context should be None since header was invalid
    assert data["trace_context"] is None


def test_trace_id_consistency_with_uuid_request_id(client):
    """Trace ID is consistently derived from request ID."""
    request_id = str(uuid4())
    response = client.get("/test", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    data = response.json()
    # Request ID should be echoed
    assert data["request_id"] == request_id
    # Trace ID should be derived from it consistently
    expected_trace_id = request_id.replace("-", "")
    assert data["trace_id"] == expected_trace_id


def test_traceparent_takes_precedence_over_generated_trace_id(client):
    """When traceparent header is present, it overrides auto-generated trace_id."""
    traceparent = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa0-bbbbbbbbbbbbbb00-00"
    request_id = str(uuid4())
    response = client.get(
        "/test",
        headers={
            "X-Request-ID": request_id,
            "traceparent": traceparent,
        },
    )
    assert response.status_code == 200
    data = response.json()
    # Request ID from header
    assert data["request_id"] == request_id
    # Trace context should come from traceparent, not derived from request_id
    assert data["trace_context"] is not None
    assert data["trace_context"]["trace_id"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa0"


def test_trace_context_is_isolated_between_requests(app_with_trace_context):
    """Trace context doesn't leak between concurrent requests."""
    client = TestClient(app_with_trace_context)

    traceparent1 = "00-1111111111111111111111111111111a-aaaaaaaaaaaaaaaa-01"
    response1 = client.get("/test", headers={"traceparent": traceparent1})
    assert (
        response1.json()["trace_context"]["trace_id"]
        == "1111111111111111111111111111111a"
    )

    # Second request with different traceparent
    traceparent2 = "00-2222222222222222222222222222222b-bbbbbbbbbbbbbbbb-00"
    response2 = client.get("/test", headers={"traceparent": traceparent2})
    assert (
        response2.json()["trace_context"]["trace_id"]
        == "2222222222222222222222222222222b"
    )

    # Verify they're different
    assert (
        response1.json()["trace_context"]["trace_id"]
        != response2.json()["trace_context"]["trace_id"]
    )


def test_trace_context_cleanup_after_request(client):
    """After a request completes, trace context is cleaned up."""
    response = client.get("/test")
    assert response.status_code == 200

    # Outside of a request context, get_trace_context should return None
    assert get_trace_context() is None
