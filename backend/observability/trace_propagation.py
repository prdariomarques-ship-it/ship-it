"""Trace context propagation helpers for distributed tracing across 6 mechanisms:
HTTP (inbound/outbound), database, external APIs, jobs, event bus, agent orchestrator.

All mechanisms work with the W3C TraceContext standard (traceparent header format)
and maintain parent-child span relationships across async boundaries.
"""
from typing import Optional

from observability.request_context import get_request_id, get_trace_id
from middleware.trace_context import get_trace_context


def get_current_trace_context() -> Optional[dict[str, str]]:
    """Get current trace context from request scope.

    Returns upstream traceparent context if present, else derives context
    from request_id + trace_id. Used by all propagation mechanisms.
    """
    # First check if we have a traceparent header context (upstream propagation)
    upstream_context = get_trace_context()
    if upstream_context:
        return upstream_context

    # Otherwise, derive from request_id/trace_id (generated at request entry)
    trace_id = get_trace_id()
    if trace_id:
        return {
            "version": "00",
            "trace_id": trace_id,
            "span_id": "0000000000000000",  # Placeholder; instrumentation overrides
            "trace_flags": "01",  # Sampled
        }

    return None


def format_traceparent(trace_context: dict[str, str]) -> str:
    """Format trace context as W3C traceparent header.

    Format: 00-{trace_id}-{span_id}-{trace_flags}
    """
    return (
        f"{trace_context.get('version', '00')}-"
        f"{trace_context.get('trace_id', '0'*32)}-"
        f"{trace_context.get('span_id', '0'*16)}-"
        f"{trace_context.get('trace_flags', '01')}"
    )


def inject_trace_header(headers: dict[str, str]) -> None:
    """Inject traceparent header into outgoing HTTP request headers.

    Modifies headers dict in-place. Used by httpx and external API calls.
    """
    trace_context = get_current_trace_context()
    if trace_context:
        headers["traceparent"] = format_traceparent(trace_context)


def serialize_trace_context() -> Optional[dict[str, str]]:
    """Serialize current trace context for storage (e.g., in job payload).

    Used by Job Worker to preserve trace context across async job execution.
    """
    return get_current_trace_context()


def restore_trace_context(trace_data: Optional[dict[str, str]]) -> Optional[dict[str, str]]:
    """Restore trace context from serialized data.

    Used by Job Worker and Event Bus handlers to resume tracing.
    """
    if isinstance(trace_data, dict) and "trace_id" in trace_data:
        return trace_data
    return None
