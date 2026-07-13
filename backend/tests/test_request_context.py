"""Request/Correlation ID context management — one id per request."""
import uuid

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from observability.request_context import (
    REQUEST_ID_HEADER,
    RequestIDMiddleware,
    get_request_id,
)


@pytest.fixture
def app_with_middleware():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    async def test_route():
        return {"request_id": get_request_id()}

    return app


@pytest.fixture
def client(app_with_middleware):
    return TestClient(app_with_middleware)


def test_request_id_is_generated_when_not_provided(client):
    """When no X-Request-ID header is sent, a new UUID is generated."""
    response = client.get("/test")
    assert response.status_code == 200
    request_id = response.json()["request_id"]
    assert request_id is not None
    # Should be a valid UUID
    try:
        uuid.UUID(request_id)
    except ValueError:
        pytest.fail(f"Invalid UUID format: {request_id}")


def test_request_id_is_propagated_from_header(client):
    """When X-Request-ID header is provided, it's used instead of generating a new one."""
    test_id = "test-request-id-12345"
    response = client.get("/test", headers={REQUEST_ID_HEADER: test_id})
    assert response.status_code == 200
    assert response.json()["request_id"] == test_id


def test_request_id_is_echoed_in_response_header(client):
    """The response includes the request ID in X-Request-ID header."""
    test_id = "test-request-id-echo"
    response = client.get("/test", headers={REQUEST_ID_HEADER: test_id})
    assert response.headers[REQUEST_ID_HEADER] == test_id


def test_request_id_is_echoed_in_response_header_when_generated(client):
    """Generated request IDs are echoed in the response header."""
    response = client.get("/test")
    assert REQUEST_ID_HEADER in response.headers
    response_id = response.headers[REQUEST_ID_HEADER]
    assert response_id == response.json()["request_id"]


def test_request_id_context_is_cleaned_up_after_request(client):
    """After a request completes, the request ID context is cleaned up."""
    # Make a request with a specific ID
    test_id = "test-cleanup"
    response = client.get("/test", headers={REQUEST_ID_HEADER: test_id})
    assert response.status_code == 200

    # Outside of a request context, get_request_id should return None
    assert get_request_id() is None


def test_multiple_concurrent_requests_maintain_separate_ids(app_with_middleware):
    """Multiple clients can make requests with different request IDs."""
    client1 = TestClient(app_with_middleware)
    client2 = TestClient(app_with_middleware)

    id1 = "request-1"
    id2 = "request-2"

    response1 = client1.get("/test", headers={REQUEST_ID_HEADER: id1})
    response2 = client2.get("/test", headers={REQUEST_ID_HEADER: id2})

    assert response1.json()["request_id"] == id1
    assert response2.json()["request_id"] == id2
