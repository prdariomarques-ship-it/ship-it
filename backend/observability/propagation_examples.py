"""Example integrations for trace context propagation across 5 mechanisms.

These examples show how each mechanism uses the trace propagation helpers
to maintain parent-child span relationships and context continuity.
"""

from contextvars import ContextVar
from typing import Optional

from observability.trace_propagation import (
    serialize_trace_context,
    restore_trace_context,
    inject_trace_header,
    get_current_trace_context,
)

# Context variable for Job Worker to preserve trace across async boundaries
_job_trace_context: ContextVar[Optional[dict[str, str]]] = ContextVar(
    "job_trace_context", default=None
)


# ============================================================================
# Mechanism 3: SQLAlchemy Database Query Propagation
# ============================================================================


class SQLAlchemyTraceIntegration:
    """SQLAlchemy propagation: trace context available during query execution.

    OpenTelemetry's SQLAlchemy instrumentor automatically captures queries.
    Trace context from request scope is available to the instrumentor.
    """

    @staticmethod
    def example_query_with_trace():
        """Example: Query executes within request trace context.

        The trace context from get_current_trace_context() is available
        to OpenTelemetry's SQLAlchemy instrumentor during query execution.
        """
        trace_context = get_current_trace_context()
        # During actual query execution:
        # session.execute(query)
        # OpenTelemetry SQLAlchemy instrumentor will create span with this context
        return trace_context


# ============================================================================
# Mechanism 6: httpx External API Propagation
# ============================================================================


class HttpxTraceIntegration:
    """httpx propagation: trace context injected into external API calls.

    Outbound HTTP requests to external services receive traceparent header
    to maintain trace continuity across service boundaries.
    """

    @staticmethod
    def example_api_call_with_trace():
        """Example: API call includes traceparent header.

        When making a request to external API:
        ```python
        headers = {}
        inject_trace_header(headers)  # Adds traceparent
        response = await client.get("https://api.example.com/data", headers=headers)
        ```

        The external service receives traceparent and can continue the trace.
        """
        headers = {}
        inject_trace_header(headers)
        return headers


# ============================================================================
# Mechanism 4: Job Worker Background Task Propagation
# ============================================================================


class JobWorkerTraceIntegration:
    """Job Worker propagation: trace context serialized in job payload.

    When enqueueing a job, serialize trace context. When executing handler,
    restore context before handler runs so nested operations are traced.
    """

    @staticmethod
    def enqueue_job_with_trace(job_name: str, payload: dict) -> dict:
        """Enqueue a job, serializing current trace context.

        This is called during request processing (HTTP handler).
        """
        job_payload = dict(payload)
        trace_context = serialize_trace_context()
        if trace_context:
            job_payload["__trace_context"] = trace_context
        return job_payload

    @staticmethod
    async def execute_job_handler(handler, job_payload: dict) -> None:
        """Execute job handler with trace context restored.

        This is called by JobWorker._execute() before calling handler.
        """
        trace_context = job_payload.get("__trace_context")
        restored = restore_trace_context(trace_context)

        if restored:
            # Set trace context for this job's execution
            token = _job_trace_context.set(restored)
            try:
                await handler(job_payload)
            finally:
                _job_trace_context.reset(token)
        else:
            # No trace context; execute normally
            await handler(job_payload)


# ============================================================================
# Mechanism 5: Event Bus Trace Propagation
# ============================================================================


class EventBusTraceIntegration:
    """Event Bus propagation: trace context serialized in event payload.

    When publishing an event, include trace context. When handler processes
    event, restore context so nested operations maintain trace continuity.
    """

    @staticmethod
    def publish_event_with_trace(event_name: str, payload: dict) -> dict:
        """Publish event with trace context included.

        This is called during request/handler processing.
        """
        event_payload = dict(payload)
        trace_context = serialize_trace_context()
        if trace_context:
            event_payload["__trace_context"] = trace_context
        return event_payload

    @staticmethod
    async def handle_event_with_trace(handler, event) -> None:
        """Handle event with trace context restored.

        This is called by EventBus for each registered handler.
        """
        trace_context = event.payload.get("__trace_context")
        restored = restore_trace_context(trace_context)

        if restored:
            # Set trace context for this handler's execution
            token = _job_trace_context.set(restored)
            try:
                await handler(event)
            finally:
                _job_trace_context.reset(token)
        else:
            # No trace context; execute normally
            await handler(event)


# ============================================================================
# Mechanism 7: Agent Orchestrator Propagation
# ============================================================================


class AgentOrchestratorTraceIntegration:
    """Agent Orchestrator propagation: trace context available during execution.

    Agents running during request processing have access to current trace
    context. Tool calls made by agents inherit parent span context.
    """

    @staticmethod
    def get_agent_trace_context() -> Optional[dict[str, str]]:
        """Get current trace context for agent execution.

        Agents can call this to retrieve context for logging, metrics,
        or to pass to nested tool calls.
        """
        return get_current_trace_context()

    @staticmethod
    async def execute_agent_tool_with_trace(tool_name: str, tool_fn, args: dict):
        """Execute agent tool with trace context inherited from parent.

        The tool function executes within the agent's trace context,
        so any nested operations (API calls, DB queries) are traced.
        """
        # Tool function executes in current request context
        # Trace context is automatically available via ContextVar
        result = await tool_fn(**args)
        return result


# ============================================================================
# Parent-Child Span Continuity Patterns
# ============================================================================


class ParentChildSpanPatterns:
    """Patterns for maintaining parent-child span relationships."""

    @staticmethod
    def http_to_job_chain():
        """Pattern: HTTP request → enqueue job → job handler.

        Trace continuity:
        1. HTTP request received with/without traceparent
        2. Trace context generated (from traceparent or request_id)
        3. Job enqueued with trace context in payload
        4. Job handler executes with restored trace context
        5. All nested operations (queries, events) inherit trace
        """
        pass

    @staticmethod
    def http_to_api_call_chain():
        """Pattern: HTTP request → call external API.

        Trace continuity:
        1. HTTP request received with trace context
        2. Outbound API call injects traceparent header
        3. External service receives traceparent and continues trace
        4. Responses include trace context for correlation
        """
        pass

    @staticmethod
    def http_to_event_to_handler_chain():
        """Pattern: HTTP request → publish event → handle event.

        Trace continuity:
        1. HTTP request received with trace context
        2. Event published with trace context in payload
        3. Event handler executes with restored trace context
        4. Any operations in handler inherit trace
        """
        pass

    @staticmethod
    def agent_to_tool_to_api_chain():
        """Pattern: Agent execution → tool call → external API.

        Trace continuity:
        1. Agent starts within HTTP request trace context
        2. Agent calls tool (inherits parent trace context)
        3. Tool makes API call (injects traceparent header)
        4. All operations from agent through API are in same trace
        """
        pass
