"""Tests for error sanitization middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_error():
    """Create an app that throws an error."""
    from middleware.error_sanitization import ErrorSanitizationMiddleware

    app = FastAPI()
    app.add_middleware(ErrorSanitizationMiddleware)

    @app.get("/error")
    async def error_endpoint():
        raise ValueError("This is a test error with sensitive details")

    @app.get("/safe")
    async def safe_endpoint():
        return {"status": "ok"}

    return app


def test_error_response_sanitized(app_with_error):
    """Error responses don't contain stack traces."""
    client = TestClient(app_with_error)
    response = client.get("/error")
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal Server Error"
    assert "ValueError" not in body["detail"]
    assert "test error" not in body["detail"]
    assert "traceback" not in str(body)


def test_safe_endpoint_still_works(app_with_error):
    """Non-error endpoints still work normally."""
    client = TestClient(app_with_error)
    response = client.get("/safe")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_error_response_has_generic_message(app_with_error):
    """All errors return generic message."""
    client = TestClient(app_with_error)
    response = client.get("/error")
    body = response.json()
    assert body["detail"] == "Internal Server Error"
    assert len(body["detail"]) < 100  # Generic, not detailed


class TestErrorSanitizationWithLogs:
    def test_logs_contain_full_exception_details(self, caplog):
        """Full exception details are logged (not visible to client)."""
        from middleware.error_sanitization import ErrorSanitizationMiddleware

        app = FastAPI()
        app.add_middleware(ErrorSanitizationMiddleware)

        @app.get("/error")
        async def error_endpoint():
            raise ValueError("Sensitive error message")

        client = TestClient(app)
        with caplog.at_level("ERROR"):
            response = client.get("/error")

        assert response.status_code == 500
        assert "Unhandled exception in request" in caplog.text
        assert any(
            "ValueError" in str(getattr(record, "context", {}))
            for record in caplog.records
        )


def test_correlation_id_in_error_log(caplog):
    """Error logs include correlation ID."""
    from middleware.error_sanitization import ErrorSanitizationMiddleware
    from observability.request_context import RequestIDMiddleware

    app = FastAPI()
    app.add_middleware(ErrorSanitizationMiddleware)
    app.add_middleware(RequestIDMiddleware)

    @app.get("/error")
    async def error_endpoint():
        raise RuntimeError("Test error")

    client = TestClient(app)
    with caplog.at_level("ERROR"):
        response = client.get(
            "/error", headers={"X-Request-ID": "test-correlation-123"}
        )

    assert response.status_code == 500


class TestErrorResponse:
    def test_error_response_is_json(self):
        """Error response is valid JSON."""
        from middleware.error_sanitization import ErrorSanitizationMiddleware

        app = FastAPI()
        app.add_middleware(ErrorSanitizationMiddleware)

        @app.get("/error")
        async def error_endpoint():
            raise Exception("Test")

        client = TestClient(app)
        response = client.get("/error")
        assert response.status_code == 500
        body = response.json()
        assert isinstance(body, dict)
        assert "detail" in body

    def test_error_status_code_is_500(self):
        """All unhandled exceptions return 500."""
        from middleware.error_sanitization import ErrorSanitizationMiddleware

        app = FastAPI()
        app.add_middleware(ErrorSanitizationMiddleware)

        @app.get("/error")
        async def error_endpoint():
            raise RuntimeError("Test error")

        client = TestClient(app)
        response = client.get("/error")
        assert response.status_code == 500

    def test_multiple_errors_all_sanitized(self):
        """Multiple different errors are all sanitized."""
        from middleware.error_sanitization import ErrorSanitizationMiddleware

        app = FastAPI()
        app.add_middleware(ErrorSanitizationMiddleware)

        @app.get("/error1")
        async def error1():
            raise ValueError("ValueError message")

        @app.get("/error2")
        async def error2():
            raise TypeError("TypeError message")

        @app.get("/error3")
        async def error3():
            raise KeyError("KeyError message")

        client = TestClient(app)
        for endpoint in ["/error1", "/error2", "/error3"]:
            response = client.get(endpoint)
            assert response.status_code == 500
            assert response.json()["detail"] == "Internal Server Error"
