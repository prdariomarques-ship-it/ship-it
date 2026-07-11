"""Request/Correlation ID: one id per inbound request, propagated through
logs, the response, and (when tracing is enabled) the trace span — without
every call site needing to pass it explicitly.

Read `X-Request-ID` from the caller when present (lets an upstream proxy or
another service propagate its own id across the whole chain); otherwise mint
a new UUID4. Always echoed back on the response so the caller can correlate
their request with what shows up in our logs/traces.
"""
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Current request's id, or None outside of a request (e.g. the job worker)."""
    return _request_id.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        token = _request_id.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
