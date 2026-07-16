"""Request/Correlation ID and Trace ID: one id per inbound request, propagated
through logs, the response, and (when tracing is enabled) the trace span —
without every call site needing to pass it explicitly.

Read `X-Request-ID` from the caller when present (lets an upstream proxy or
another service propagate its own id across the whole chain); otherwise mint
a new UUID4. Always echoed back on the response so the caller can correlate
their request with what shows up in our logs/traces.

Trace ID is a 32-character hex string (128-bit) derived from the request ID
(UUID4). This creates a 1:1 correlation between request_id and trace_id so
every request's logs, metrics, and traces can be queried together.
"""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def get_request_id() -> str | None:
    """Current request's id, or None outside of a request (e.g. the job worker)."""
    return _request_id.get()


def get_trace_id() -> str | None:
    """Current request's trace id (32-char hex), or None outside of a request."""
    return _trace_id.get()


def _uuid_to_trace_id(request_id: str) -> str:
    """Convert UUID4 request_id to 32-character hex trace_id for W3C TraceContext.

    This ensures a 1:1 correlation between request_id and trace_id — every
    request's logs, metrics, and traces are queryable together by either id.
    """
    try:
        uuid_obj = uuid.UUID(request_id)
        return uuid_obj.hex
    except (ValueError, AttributeError):
        return request_id.replace("-", "")[:32]


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        trace_id = _uuid_to_trace_id(request_id)

        token_request = _request_id.set(request_id)
        token_trace = _trace_id.set(trace_id)
        try:
            response = await call_next(request)
        finally:
            _trace_id.reset(token_trace)
            _request_id.reset(token_request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
