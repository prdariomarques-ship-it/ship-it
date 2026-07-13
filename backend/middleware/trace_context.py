"""W3C Trace Context standard (RFC 9110): extract and propagate traceparent header.

Format: traceparent = 00-{trace_id}-{span_id}-{trace_flags}
  - 00: version (currently always 00)
  - {trace_id}: 32 hex characters (128-bit UUID-like identifier for the entire trace)
  - {span_id}: 16 hex characters (64-bit identifier for this span)
  - {trace_flags}: 2 hex characters (trace-flags; bit 0 = sampled)

When a traceparent header is present in the request, use it to correlate
this request's spans with upstream traces. When absent, a new trace begins.
"""
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_trace_context: ContextVar[dict[str, str] | None] = ContextVar("trace_context", default=None)


def get_trace_context() -> Optional[dict[str, str]]:
    """Current trace context (traceparent components), or None outside a request."""
    return _trace_context.get()


def parse_traceparent(header: str) -> Optional[dict[str, str]]:
    """Parse W3C traceparent header. Returns {version, trace_id, span_id, trace_flags} or None if invalid."""
    parts = header.split("-")
    if len(parts) != 4:
        return None
    version, trace_id, span_id, trace_flags = parts
    if len(version) != 2 or len(trace_id) != 32 or len(span_id) != 16 or len(trace_flags) != 2:
        return None
    return {"version": version, "trace_id": trace_id, "span_id": span_id, "trace_flags": trace_flags}


class TraceContextMiddleware(BaseHTTPMiddleware):
    """Extract and store W3C Trace Context from incoming requests."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        traceparent = request.headers.get("traceparent")
        trace_ctx = None

        if traceparent:
            trace_ctx = parse_traceparent(traceparent)

        token = _trace_context.set(trace_ctx)
        try:
            response = await call_next(request)
        finally:
            _trace_context.reset(token)

        return response
