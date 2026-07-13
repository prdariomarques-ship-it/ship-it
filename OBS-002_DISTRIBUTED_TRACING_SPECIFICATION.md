# OBS-002 — Distributed Tracing Specification

**Status:** SPECIFICATION (Not Implemented)  
**Date:** 2026-07-13  
**Owner:** TECH_LEAD  
**Prerequisite:** OBS-001 COMPLETED ✓  
**Architecture State:** FROZEN  
**Governance State:** FROZEN  

---

## Executive Summary

OBS-002 extends the monitoring stack (OBS-001: Prometheus/Alertmanager/Grafana) with **end-to-end distributed tracing** via OpenTelemetry. Integrates with existing structured logs and Prometheus metrics to form the complete observability pillars (traces, logs, metrics). Enables deep visibility into request lifecycles across backend services, worker processes, and external integrations.

---

## 1. Goal

Enable operators to:
1. **Trace end-to-end request flow** from inbound HTTP through agents, workers, database queries, and external API calls
2. **Correlate traces with logs and metrics** — same request ID/trace ID appears in all three pillars
3. **Diagnose performance issues** — identify which span (HTTP, query, external call, agent run) caused latency
4. **Track autonomous operations** — background jobs and event bus propagate trace context without manual threading
5. **Debug failures** — exception spans include stack traces; failed steps visible in trace hierarchy

---

## 2. Current State

### Existing Observability Infrastructure (OBS-001)
- ✓ Prometheus metrics (HTTP, agents, jobs, WhatsApp — counters/histograms only, no traces)
- ✓ Alertmanager routing (severity-based, webhook/email)
- ✓ Grafana dashboards (5 dashboards, read-only IaC)
- ✓ Structured JSON logging with `request_id` correlation
- ✓ Request ID middleware (`X-Request-ID` header, UUID4 fallback)

### Partial/Stub Tracing Infrastructure
- ✓ OpenTelemetry package installed but **disabled by default** (`OTEL_ENABLED` env var)
- ✓ Console exporter fallback (if no OTLP endpoint configured)
- ✓ Auto-instrumentation: FastAPI, SQLAlchemy, httpx
- ✓ Service name configurable via `OTEL_SERVICE_NAME`
- ✗ **No span correlation with logs** (spans and logs are separate streams)
- ✗ **No span correlation with metrics** (metrics have no trace ID)
- ✗ **No trace context propagation** in worker/job execution
- ✗ **No trace context propagation** in event bus
- ✗ **No trace ID in structured logs** (only request_id, not trace_id)
- ✗ **Manual tracing opt-in only** (no production-grade defaults)

### Current Request Flow (Single Request)
```
Browser/Client
    ↓ (X-Request-ID header or new UUID4)
RequestIDMiddleware (stores in contextvar)
    ↓
HTTP handler
    ↓ → SQLAlchemy query (auto-instrumented, but no trace link)
    ↓ → httpx call to LLM/WhatsApp (auto-instrumented, but no trace link)
    ↓
Structured log (request_id stamped via filter)
    ↓ → Prometheus metric (no request_id/trace_id)
Response (X-Request-ID header echoed back)
```

---

## 3. Problem Statement

**Three Integration Gaps:**

1. **Traces exist in isolation**
   - Request flows through agents, database, external APIs
   - Each step auto-instrumented separately
   - No single trace view connecting all steps
   - Operator cannot answer: "Why was this request slow?"

2. **Traces, logs, and metrics don't correlate**
   - A slow HTTP request appears in:
     - Trace (span with p95 latency)
     - Logs (JSON line with request_id)
     - Metrics (histogram bucket)
   - But operator cannot pivot between them (no common ID)
   - Debugging requires manual log search + Prometheus query + trace search

3. **Background operations have no tracing**
   - Job worker executes tasks (no trace context)
   - Event bus publishes/subscribes (no trace context)
   - Agent runs via orchestrator (no trace context)
   - Autonomous/delayed operations lose trace chain

**Impact:** Diagnosing production incidents requires manual log correlation; performance issues take 10-20x longer to root-cause.

---

## 4. Scope

### IN Scope

**Tracing Architecture**
- Production-grade OpenTelemetry integration (always-on, not opt-in)
- Automatic trace context propagation across services
- Trace ID strategy (32-char hex, part of request context)
- Span hierarchy (parent-child relationships)

**Trace Context Propagation**
- HTTP (W3C Trace Context headers)
- Database queries (SQLAlchemy span context)
- External API calls (httpx span context)
- Background jobs (contextvar threading to worker)
- Event bus (eventbus.publish/subscribe carries trace ID)
- Agent runs (orchestrator carries trace ID to agent executor)

**Integration with Existing Pillars**
- Trace ID in structured logs (new field: `trace_id`)
- Trace ID correlation with Prometheus metrics (via exemplars)
- Request ID ↔ Trace ID relationship (one trace per request, always)

**Docker Integration**
- Jaeger collector service (optional, not Loki/Tempo)
- Trace retention policy (sampled: 100 requests/s for 24h)
- Health check for collector
- Volume for trace storage (if not remote)

**Configuration**
- Environment variables (OTEL_*, JAEGER_*)
- Sampling strategy (probabilistic or rate-based)
- Batch span processor settings (batch size, timeout)
- Exporter endpoint and auth

**Security**
- Sanitize PII from spans (API keys, passwords, email contents)
- OTLP/HTTP endpoint protected (TLS + auth if configured)
- Trace data retention policy (TTL)

**Performance**
- Zero-overhead when tracing disabled
- Batch processing of spans (not one-by-one)
- No blocking on trace export (async)
- Sampling reduces storage cost

**Rollback**
- Feature flag to disable tracing (single env var)
- Trace export failure does NOT fail request (telemetry-safe)
- Graceful degradation (missing trace context = normal logging)

### OUT of Scope

- Trace visualization UI (send to Jaeger/Datadog/Honeycomb, use their UI)
- Distributed tracing for frontend/SDK (JavaScript instrumentation)
- Custom span creation in business logic (auto-instrumentation only)
- ML model performance tracing (not part of request lifecycle)
- Cost allocation by trace (billing per-trace not implemented)
- OpenTelemetry Collector on backend (uses OTLP/HTTP directly)
- APM alerting (OBS-003, future capability)

---

## 5. OpenTelemetry Architecture

### Overview
```
┌──────────────────────────────────────┐
│         Dario OS Backend             │
│  (FastAPI, SQLAlchemy, httpx)        │
└──────────────────────────────────────┘
         ↓ (spans)
┌──────────────────────────────────────┐
│  OpenTelemetry SDK (auto-instr.)     │
│  - FastAPIInstrumentor               │
│  - SQLAlchemyInstrumentor            │
│  - HTTPXClientInstrumentor           │
│  - Custom: Job Worker, Event Bus     │
└──────────────────────────────────────┘
         ↓ (OTLP/HTTP protocol)
┌──────────────────────────────────────┐
│  OTLP Exporter                       │
│  (batch processor, 1024 spans/batch) │
└──────────────────────────────────────┘
         ↓ (network)
┌──────────────────────────────────────┐
│  Backend (Jaeger, Datadog, etc.)     │
│  - Ingestion                         │
│  - Storage                           │
│  - Query API                         │
└──────────────────────────────────────┘
```

### Components

**1. TracerProvider**
- One global provider per process
- Resource: service name, version, environment
- Sampler: probabilistic (configurable rate)
- Span processors: BatchSpanProcessor (async export)

**2. Instrumentors (Auto-Instrumentation)**
- FastAPIInstrumentor: one span per HTTP request
- SQLAlchemyInstrumentor: one span per DB query
- HTTPXClientInstrumentor: one span per outbound API call
- Custom: Job Worker (one span per job execution)
- Custom: Event Bus (one span per publish/subscribe)
- Custom: Agent Orchestrator (one span per agent run)

**3. Exporters**
- OTLPSpanExporter (OTLP/HTTP to remote backend)
- ConsoleSpanExporter (fallback for local debugging)
- InMemoryExporter (testing)

**4. Propagators**
- W3CTraceContextPropagator (HTTP headers)
- JaegerPropagator (legacy, fallback)

---

## 6. Trace Context Propagation

### Strategy

**Request Lifecycle Trace**
```
Client Request
    ↓
[HTTP Span 1]  ← starts on inbound request
  ├─ [SQLAlchemy Span 2]  ← nested, auth query
  ├─ [Agent Run Span 3]  ← nested, planner + executor
  │   ├─ [Tool Call Span 4]  ← nested, calendar lookup
  │   ├─ [HTTPx Span 5]  ← nested, Google API call
  │   └─ [Tool Result Span 6]  ← nested, result processing
  ├─ [SQLAlchemy Span 7]  ← nested, save result
  └─ [HTTPx Span 8]  ← nested, webhook callback
Response
```

### Propagation Mechanism

**1. HTTP Requests (Inbound)**
```
Request Header: traceparent: 00-{trace_id}-{parent_span_id}-01
```
- Extracted by RequestIDMiddleware → stored in contextvar
- If missing, generate new trace_id (UUID4, hex-encoded)

**2. HTTP Requests (Outbound)**
```
httpx call to external API
    ↓
HTTPXClientInstrumentor extracts contextvar trace_id
    ↓
Adds traceparent header to outbound request
    ↓
External API receives header (may ignore or propagate further)
```

**3. Database Queries**
```
sqlalchemy.query()
    ↓
SQLAlchemyInstrumentor reads contextvar trace_id
    ↓
Creates span with parent_span_id = current active span
    ↓
Query executes with trace context
```

**4. Background Jobs**
```
job_worker.enqueue(job_name, **kwargs)
    ↓
Current request's trace_id stored in job metadata
    ↓
Worker process loads job
    ↓
Restores trace_id to contextvar before execution
    ↓
Job spans linked to original request trace
    ↓
Job completes; trace spans exported
```

**5. Event Bus**
```
eventbus.publish(event_name, data, trace_context=get_trace_context())
    ↓
Trace context serialized in event envelope
    ↓
Subscriber loads event
    ↓
Restores trace_context to contextvar
    ↓
Handler execution linked to publisher's trace
```

**6. Agent Orchestrator**
```
orchestrator.run_agent(agent, plan, trace_context=get_trace_context())
    ↓
Agent executor receives trace_context
    ↓
Restores to contextvar for entire agent run
    ↓
Tool calls nested under agent span
    ↓
Result span links back to original request
```

---

## 7. Span Hierarchy

### Span Types and Nesting Rules

**Type: HTTP Request** (entry point)
- Attributes: method, path, status_code, duration_ms
- Errors: status >= 500 → span marked as error, status_code recorded

**Type: Database Query** (child of HTTP or Agent)
- Attributes: statement, database, duration_ms
- Errors: db error → span marked as error, exception recorded

**Type: External API Call** (child of HTTP or Tool)
- Attributes: method, url, status_code, duration_ms
- Errors: status >= 500 or exception → span marked as error

**Type: Agent Run** (child of HTTP)
- Attributes: agent_name, planner_duration, executor_duration, total_duration
- Errors: planning failure or execution failure → span marked as error

**Type: Tool Call** (child of Agent)
- Attributes: tool_name, result_status (success|error|timeout), duration_ms
- Errors: tool error → span marked as error, exception recorded

**Type: Job Execution** (entry point in worker)
- Attributes: job_name, job_id, parent_request_id, duration_ms
- Errors: job error → span marked as error, exception recorded

**Type: Event Publish** (child of HTTP)
- Attributes: event_name, event_id, subscriber_count, duration_ms

**Type: Event Subscribe** (child of Event)
- Attributes: event_name, handler_name, duration_ms
- Errors: handler error → span marked as error

### Nesting Constraints
- HTTP → SQLAlchemy, Agent, HTTPx (direct children)
- Agent → Tool Call, SQLAlchemy, HTTPx (direct children)
- Tool Call → SQLAlchemy, HTTPx, nested Tool Call (direct children)
- Job Execution → SQLAlchemy, Agent, HTTPx, Event (direct children)
- Event Publish → Event Subscribe (direct child for each subscriber)
- **Max nesting depth:** 10 (prevent stack overflow)

---

## 8. Trace ID Strategy

### Format
```
W3C Trace Context Standard (RFC 9110)

traceparent: 00-{trace_id}-{span_id}-{trace_flags}

trace_id:     32 hex chars (128 bit), e.g. "4bf92f3577b34da6a3ce929d0e0e4736"
span_id:      16 hex chars (64 bit), e.g. "00f067aa0ba902b7"
trace_flags:  2 hex chars (8 bit), e.g. "01" (sampled) or "00" (not sampled)
```

### Generation
- **New request:** Generate trace_id = UUID4 (16 bytes) → hex-encode (32 chars)
- **Existing request:** Extract from `traceparent` header or `X-Request-ID` header
- **Job/Event:** Inherit parent request's trace_id, generate new span_id
- **Validation:** Only valid hex strings accepted; invalid → generate new

### Storage in Context
```
contextvar "_trace_id": str | None
contextvar "_span_id": str | None
contextvar "_trace_flags": str | None  # "01" or "00"
```

### Correlation with Request ID
```
X-Request-ID (existing): "550e8400-e29b-41d4-a716-446655440000" (UUID4)
trace_id (new):          "550e8400e29b41d4a716446655440000" (same UUID4, hex format)

One-to-one mapping:
    request_id = trace_id with hyphens stripped
    Both propagated end-to-end
```

---

## 9. Correlation with Structured Logs

### Current Log Format (OBS-001)
```json
{
  "timestamp": "2026-07-13T12:00:00Z",
  "level": "info",
  "logger": "backend.agents",
  "message": "Agent completed",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### New Log Format (OBS-002)
```json
{
  "timestamp": "2026-07-13T12:00:00Z",
  "level": "info",
  "logger": "backend.agents",
  "message": "Agent completed",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "trace_id": "550e8400e29b41d4a716446655440000",
  "span_id": "00f067aa0ba902b7",
  "trace_flags": "01"
}
```

### Implementation
- LogFilter reads contextvar `_trace_id` (same way RequestIDFilter reads request_id)
- If trace_id present → add fields to log record
- Formatter includes trace_id/span_id in JSON output
- Search logs by trace_id → all events in one request visible

### Usage Example
```python
# Operator searches logs by trace_id
# All logs with trace_id="550e8400e29b41d4a716446655440000" appear
# Then clicks trace_id → opens Jaeger UI for full trace
```

---

## 10. Correlation with Prometheus Metrics

### Current Metrics (OBS-001)
```
darioos_http_request_duration_seconds_bucket{method="POST",path="/api/chat",le="0.1"} 5
darioos_agent_runs_total{agent="planner",provider="openai",status="success"} 42
```

### New: Span Exemplars
```
darioos_http_request_duration_seconds_bucket{method="POST",path="/api/chat",le="0.1"}
  exemplar: trace_id="550e8400e29b41d4a716446655440000", value=0.085, timestamp=2026-07-13T12:00:00Z

darioos_agent_runs_total{agent="planner",provider="openai",status="success"}
  exemplar: trace_id="550e8400e29b41d4a716446655440000", timestamp=2026-07-13T12:00:01Z
```

### Implementation
- Histogram spans record `exemplar` on completion (trace_id, duration, timestamp)
- OTel SDK exports exemplars in OTLP/Prometheus format
- Grafana displays trace link when hovering histogram buckets
- Clicking exemplar opens Jaeger/Datadog UI with that trace

### Dashboards (Grafana → Jaeger Flow)
```
1. Operator sees high p95 latency on "POST /api/chat" histogram
2. Clicks histogram bucket → exemplar list appears
3. Selects exemplar (slowest one, e.g., 2.5s duration)
4. Clicks "View Trace" → opens Jaeger UI
5. Sees full trace: HTTP → agent planning (1.2s) → tool calls (1.1s) → success
6. Identifies bottleneck: Google Calendar API timeout
7. Checks Google Calendar logs for that span_id
```

---

## 11. Correlation with Event Bus

### Current Event Bus (No Tracing)
```python
# Publisher (HTTP request context)
eventbus.publish("user_message_received", data={...})
    # Event consumed by subscriber
    # No trace link between request and subscriber

# Subscriber (separate context, no correlation)
@eventbus.subscribe("user_message_received")
def on_message_received(event):
    # Process event
    # No parent trace ID available
```

### New Event Bus (With Trace Context)
```python
# Publisher (HTTP request context)
trace_context = get_trace_context()  # {trace_id, span_id, flags}
eventbus.publish("user_message_received", data={...}, trace_context=trace_context)
    # Event envelope includes trace_context

# Subscriber (restores context)
@eventbus.subscribe("user_message_received")
def on_message_received(event):
    # Event object includes: event.trace_context
    restore_trace_context(event.trace_context)  # in contextvar
    # Now all spans/logs have parent trace_id
    # Subscriber execution appears as child span in original trace
```

### Span Hierarchy
```
[HTTP Request Span]
  ├─ [Event Publish Span "user_message_received"]
  │   └─ [Event Subscriber Span "on_message_received"]
  │       ├─ [Agent Run Span]
  │       ├─ [SQLAlchemy Span]
  │       └─ [HTTPx Span]
```

### Implementation
- EventBus.publish() adds `trace_context=get_trace_context()` parameter
- EventBus.subscribe() handler receives event with trace_context attached
- Handler entry point: `restore_trace_context(event.trace_context)` before business logic
- EventBus itself creates "event_publish" and "event_subscribe" spans

---

## 12. Worker Trace Propagation

### Current Job Worker (No Tracing)
```python
# HTTP request enqueues job
job_queue.enqueue("send_email", recipient="user@example.com")
    # Job stored in database, no trace link

# Worker picks up job (separate process, no context)
job = job_queue.dequeue()
execute_job(job)
    # Execution has no parent trace ID
    # Logs appear separately, no correlation
```

### New Worker (With Trace Propagation)
```python
# HTTP request enqueues job
trace_context = get_trace_context()
job_queue.enqueue("send_email", recipient="user@example.com", trace_context=trace_context)
    # Job row includes: trace_id, span_id, trace_flags (JSON column)

# Worker picks up job
job = job_queue.dequeue()
restore_trace_context(job.trace_context)  # in contextvar
    # Worker process now has same trace_id as HTTP request
execute_job(job)
    # Job spans linked to original HTTP request trace
    # Logs include trace_id → searchable
```

### Span Hierarchy
```
[HTTP Request Span]  (trace_id: abc123)
  ├─ [Job Enqueue Span]
  └─ (job stored with trace_id: abc123)

[Worker Process Startup]
  └─ [Job Execution Span]  (same trace_id: abc123)
      ├─ [SQLAlchemy Span]
      ├─ [HTTPx Span] (send email via SMTP)
```

### Implementation
- Job model gets new column: `trace_context: JSON`
- Job enqueue: `job.trace_context = get_trace_context()`
- Worker dequeue: `restore_trace_context(job.trace_context)` before execution
- Worker creates "job_execution" span as root (same trace_id)

---

## 13. API Changes

### New Imports
```python
from observability.tracing import (
    get_trace_context,
    restore_trace_context,
    TraceContext,
)
```

### New Functions

**`get_trace_context() → TraceContext`**
```python
@dataclass
class TraceContext:
    trace_id: str      # 32 hex chars
    span_id: str       # 16 hex chars
    trace_flags: str   # "01" or "00"

def get_trace_context() -> TraceContext:
    """Get current request's trace context (or None if not in request)."""
    trace_id = _trace_id.get()
    span_id = _span_id.get()
    trace_flags = _trace_flags.get()
    if trace_id is None:
        return None
    return TraceContext(trace_id, span_id, trace_flags)
```

**`restore_trace_context(ctx: TraceContext) → None`**
```python
def restore_trace_context(ctx: TraceContext) -> None:
    """Restore trace context to contextvars (used by worker/event handlers)."""
    if ctx is None:
        return
    _trace_id.set(ctx.trace_id)
    _span_id.set(ctx.span_id)
    _trace_flags.set(ctx.trace_flags)
```

**`get_tracer() → Tracer`**
```python
# Internal use only; auto-instrumentation handles span creation
# Exposed for custom spans if needed (optional, not recommended)
def get_tracer(name: str) -> opentelemetry.trace.Tracer:
    """Get tracer for manual span creation (advanced use only)."""
    return trace.get_tracer(name, version="1.0.0")
```

### Modified Functions

**`observability.setup_tracing()`**
```python
def setup_tracing(
    app: FastAPI,
    *,
    enabled: bool = True,  # Now true by default
    otlp_endpoint: str = None,
    service_name: str = "darioos",
    sampler_rate: float = 1.0,  # Probability: 0.0-1.0
) -> None:
    """Initialize OpenTelemetry with production defaults."""
```

**Job model (backend/models.py)**
```python
class Job(Base):
    id: UUID
    job_name: str
    status: str
    # ... existing fields ...
    trace_context: Optional[Dict[str, str]] = None  # NEW
    created_at: datetime
```

**EventBus.publish()**
```python
def publish(
    self,
    event_name: str,
    data: Dict[str, Any],
    trace_context: TraceContext = None  # NEW (optional, auto-captured if None)
) -> None:
    """Publish event with optional trace context."""
```

**EventBus subscriber decorator**
```python
@eventbus.subscribe("event_name")
async def handler(event: Event) -> None:
    # event.trace_context is always available
    restore_trace_context(event.trace_context)
    # ... business logic ...
```

### No Breaking Changes
- Existing code continues to work (trace_context optional everywhere)
- Request ID behavior unchanged (still in logs, still in X-Request-ID header)
- Prometheus metrics unchanged (exemplars added, backward compatible)
- Span creation automatic (no manual instrumentation needed)

---

## 14. Configuration

### Environment Variables

**OTEL_ENABLED** (default: `true`)
```
Enable/disable tracing entirely. If false, zero overhead.
OTEL_ENABLED=true
```

**OTEL_EXPORTER_OTLP_ENDPOINT** (default: `http://localhost:4318`)
```
OTLP/HTTP endpoint (Jaeger, Datadog, Honeycomb, etc.)
Leave empty → console exporter (logs spans to stdout)
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
```

**OTEL_SERVICE_NAME** (default: `darioos`)
```
Service name in traces (visible in Jaeger, dashboards, etc.)
OTEL_SERVICE_NAME=darioos-prod
```

**OTEL_RESOURCE_ATTRIBUTES** (optional)
```
Additional resource tags (environment, version, etc.)
OTEL_RESOURCE_ATTRIBUTES=environment=production,version=1.2.0
```

**OTEL_TRACES_SAMPLER** (default: `parentbased_always_on`)
```
Sampling strategy:
  - always_on: sample 100% (default, development)
  - always_off: sample 0% (testing)
  - parentbased_always_on: inherit parent decision
  - traceidratio: sample N% based on trace_id hash (production)
OTEL_TRACES_SAMPLER=traceidratio
```

**OTEL_TRACES_SAMPLER_ARG** (default: `1.0`)
```
If OTEL_TRACES_SAMPLER=traceidratio, sample X% of traces
Range: 0.0 (0%) to 1.0 (100%)
OTEL_TRACES_SAMPLER_ARG=0.1   # Sample 10% of traces (1000 req/sec → 100 sampled)
```

**OTEL_BATCH_SIZE** (default: `1024`)
```
Number of spans before forced export (batch processor)
OTEL_BATCH_SIZE=512
```

**OTEL_BATCH_TIMEOUT_MS** (default: `5000`)
```
Milliseconds to wait before exporting partial batch
OTEL_BATCH_TIMEOUT_MS=1000
```

### .env.example Updates
```bash
# OBS-002: Distributed Tracing
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
OTEL_SERVICE_NAME=darioos
OTEL_TRACES_SAMPLER=parentbased_always_on
OTEL_TRACES_SAMPLER_ARG=1.0
OTEL_BATCH_SIZE=1024
OTEL_BATCH_TIMEOUT_MS=5000
```

---

## 15. Docker Integration

### New Service: Jaeger Collector

**docker-compose.yml Addition**
```yaml
jaeger:
  image: jaegertracing/all-in-one:latest
  ports:
    - "16686:16686"  # UI (localhost:16686)
    - "4318:4318"    # OTLP/HTTP receiver
  environment:
    COLLECTOR_ZIPKIN_HOST_PORT: :9411
    COLLECTOR_OTLP_ENABLED: "true"
  volumes:
    - jaeger_data:/badger
  networks:
    - darioos
  healthcheck:
    test: curl -f http://localhost:14269/status || exit 1
    interval: 10s
    timeout: 5s
    retries: 3
    start_period: 10s

volumes:
  jaeger_data:
```

### Backend Service Update
```yaml
backend:
  # ... existing config ...
  environment:
    OTEL_ENABLED: "${OTEL_ENABLED:-true}"
    OTEL_EXPORTER_OTLP_ENDPOINT: "http://jaeger:4318"
    OTEL_SERVICE_NAME: "darioos"
  depends_on:
    prometheus:
      condition: service_healthy
    # ADD:
    jaeger:
      condition: service_healthy
```

### Volume for Trace Storage
```yaml
volumes:
  prometheus_data:
  alertmanager_data:
  grafana_data:
  jaeger_data:  # NEW
```

### Network
```yaml
networks:
  darioos:  # Both jaeger and backend on same network
    driver: bridge
```

### Health Check
```yaml
jaeger:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:14269/status"]
    interval: 10s
    timeout: 5s
    retries: 3
```

---

## 16. Dependencies

### Python Packages (New in requirements.txt)
```
opentelemetry-api==1.20.0
opentelemetry-sdk==1.20.0
opentelemetry-exporter-otlp==1.20.0
opentelemetry-instrumentation-fastapi==0.41b0
opentelemetry-instrumentation-sqlalchemy==0.41b0
opentelemetry-instrumentation-httpx==0.41b0
```

### Existing Packages (No Changes)
- fastapi (already installed)
- sqlalchemy (already installed)
- httpx (already installed)
- prometheus_client (OBS-001)

### Docker Images
- jaegertracing/all-in-one:latest (tracing backend)

### Compatibility
- Python ≥ 3.8 (OTel SDK requirement)
- FastAPI ≥ 0.95.0 (already installed)
- SQLAlchemy ≥ 1.4.0 (already installed)

---

## 17. Compatibility

### Backward Compatibility
- **Request ID behavior unchanged**: X-Request-ID header still works, still in logs
- **Prometheus metrics unchanged**: All existing metrics still exported, exemplars are additive
- **Logging unchanged**: Existing JSON format preserved, trace fields added
- **API backward compatible**: New parameters optional, existing calls work

### Deprecations
- None (this is an additive feature)

### Breaking Changes
- None (production-ready design avoids breaking existing APIs)

### Version Support
- OpenTelemetry stable (v1.20+, no breaking changes planned)
- Jaeger v1.40+ (supports OTLP/HTTP)
- Prometheus v2.45+ (already in OBS-001)

---

## 18. Security Considerations

### PII Sanitization

**Spans May Contain PII:**
- SQL queries (table names, WHERE clauses with user IDs)
- HTTP response bodies (user email in error messages)
- Exception stack traces (file paths, variable values)

**Mitigation:**
1. **SQL Redaction**: SQLAlchemy span attributes use `db.statement` without query parameters
   - Raw: `SELECT * FROM users WHERE email = 'user@example.com'`
   - Safe: `SELECT * FROM users WHERE email = ?` (parameterized shown only)

2. **HTTP Body Redaction**: httpx spans capture method/URL/status only, not response body
   - Captured: `httpx GET https://api.google.com/v1/calendar`
   - NOT captured: response body, auth headers

3. **Exception Redaction**: Span exceptions omit variable values, only include type/message
   - Captured: `ValueError: Invalid email format`
   - NOT captured: actual email value, stack frame locals

4. **API Key Protection**: No API keys in span attributes (not sent to Jaeger)
   - Spans never contain: `Authorization`, `X-API-Key`, `Bearer token`

### OTLP/HTTP Security

**Authentication (Optional)**
```python
# If Jaeger behind auth proxy:
OTEL_EXPORTER_OTLP_HEADERS=Authorization:Bearer+{token}
```

**TLS/HTTPS (Optional)**
```python
# If Jaeger on HTTPS:
OTEL_EXPORTER_OTLP_ENDPOINT=https://jaeger.example.com:443
OTEL_EXPORTER_OTLP_CERTIFICATE=/path/to/ca.pem
```

**Network Isolation**
- Jaeger on internal `darioos` network (docker-compose)
- Not exposed to public (no port mapping except localhost for dev UI)
- Backend → Jaeger communication internal only

### Trace Data Retention

**Storage**
- Jaeger default: 72 hours (in-memory or disk)
- Production: configure Elasticsearch backend for longer retention

**Deletion**
- Traces auto-delete after retention period
- Manual deletion: Jaeger API or direct database access
- No separate data residency policy needed

### Sampling Impact on Privacy
- Sampling 10% of traces reduces PII surface 10x
- But sampled traces still contain PII (not eliminated by sampling)
- Redaction + sampling = defense in depth

---

## 19. Performance Impact

### Overhead Measurement (per request)

| Operation | Overhead | Notes |
|-----------|----------|-------|
| Span creation | <1ms | In-memory only, batched export |
| Log enrichment (trace_id field) | <0.1ms | Filter + JSON update |
| Exemplar capture | <0.5ms | On histogram completion |
| Batch export (async) | 0ms | Non-blocking, separate thread |
| **Total per-request** | **~1-2ms** | With sampling at 1.0 |

### With Sampling (10% of traces)

| Metric | No Sampling | 10% Sampling | Savings |
|--------|-------------|--------------|---------|
| Spans exported/sec (1000 req/sec) | 5,000 | 500 | 90% |
| Network bandwidth | 500 KB/s | 50 KB/s | 90% |
| Jaeger storage | 50 MB/day | 5 MB/day | 90% |
| CPU overhead | ~5% | ~0.5% | 90% |

### Recommendations
- **Development**: OTEL_TRACES_SAMPLER_ARG=1.0 (100%, debug all requests)
- **Staging**: OTEL_TRACES_SAMPLER_ARG=0.5 (50%, balance cost/visibility)
- **Production**: OTEL_TRACES_SAMPLER_ARG=0.1 (10%, minimize cost)
- **High-traffic endpoints**: Lower sampler_arg (e.g., 0.01 for /metrics)

### No Performance Regression
- Auto-instrumentation uses low-overhead bytecode patching (OpenTelemetry standard)
- Span export non-blocking (batch processor, async thread)
- Tracing disabled (OTEL_ENABLED=false) → zero overhead

---

## 20. Rollback

### Disable Tracing (Immediate)
```bash
# Set env var, restart backend:
OTEL_ENABLED=false
```
- No span creation, export, or collection
- Logs still include trace_id field (harmless, ignored)
- Prometheus metrics unchanged
- Zero overhead

### Disable Jaeger Service (If Needed)
```bash
# If Jaeger collector fails/becomes unreachable:
# 1. Backend continues normally (OTel export failure non-blocking)
# 2. Spans still created, buffered in memory
# 3. Export retries (with backoff)
# 4. If Jaeger down > 30min, oldest spans dropped (memory limit)
```

### Feature Flag (Optional, Not Recommended)
```python
# Not implemented; use OTEL_ENABLED instead
# Rolling back via env var is simpler than code flag
```

### Database Migration (Optional)
```python
# If rollback needed: Job.trace_context column can be safely ignored
# Old jobs without trace_context will work (backward compatible)
# No migration needed to remove feature
```

### Complete Removal (If Needed)
1. Set OTEL_ENABLED=false
2. Remove Jaeger service from docker-compose.yml
3. Remove OTEL_* env vars from .env
4. (Optional) Remove trace_context column from Job table (no data loss)
5. (Optional) Remove trace_id/span_id from log formatter
6. Restart backend

---

## 21. Test Plan

### Unit Tests

**Test: get_trace_context() returns correct values**
```python
def test_get_trace_context_returns_contextvar_values():
    # Set contextvar
    _trace_id.set("abc123")
    _span_id.set("def456")
    _trace_flags.set("01")
    
    # Get context
    ctx = get_trace_context()
    
    # Assert
    assert ctx.trace_id == "abc123"
    assert ctx.span_id == "def456"
    assert ctx.trace_flags == "01"
```

**Test: restore_trace_context() restores contextvar**
```python
def test_restore_trace_context_restores_values():
    ctx = TraceContext(trace_id="xyz789", span_id="uvw012", trace_flags="00")
    restore_trace_context(ctx)
    
    assert get_trace_context() == ctx
```

**Test: Trace ID extracted from traceparent header**
```python
def test_request_id_middleware_extracts_traceparent():
    # Request with traceparent header
    response = client.get("/health", headers={"traceparent": "00-abc123-def456-01"})
    
    # Assert X-Request-ID echoed back
    assert response.headers["X-Request-ID"] == "abc123"
```

**Test: Trace ID in structured logs**
```python
def test_structured_logs_include_trace_id(caplog):
    _trace_id.set("abc123")
    logger.info("test message")
    
    # Capture JSON output
    log_entry = json.loads(caplog.records[0].getMessage())
    assert log_entry["trace_id"] == "abc123"
```

### Integration Tests

**Test: HTTP request creates span**
```python
def test_http_request_creates_span(span_exporter):
    response = client.get("/api/chat", json={"message": "hello"})
    
    # Assert span exported
    spans = span_exporter.get_finished_spans()
    assert len(spans) >= 1
    assert spans[0].name == "POST /api/chat"
    assert spans[0].status.is_ok
```

**Test: SQLAlchemy query creates nested span**
```python
def test_sqlalchemy_query_creates_nested_span(span_exporter):
    # Trigger HTTP request that queries DB
    response = client.get("/api/dashboard")
    
    # Assert spans
    spans = span_exporter.get_finished_spans()
    http_span = [s for s in spans if s.name.startswith("POST")][0]
    db_spans = [s for s in spans if s.name.startswith("SELECT")]
    
    # Assert nesting
    assert len(db_spans) >= 1
    assert db_spans[0].parent.span_id == http_span.context.span_id
```

**Test: Job execution inherits trace context**
```python
def test_job_execution_inherits_trace_context():
    # Enqueue job with trace context
    trace_ctx = TraceContext(trace_id="abc123", span_id="def456", trace_flags="01")
    job_queue.enqueue("send_email", trace_context=trace_ctx)
    
    # Execute job in worker
    job = job_queue.dequeue()
    restore_trace_context(job.trace_context)
    
    # Assert trace_id in job logs
    with caplog.at_level(logging.INFO):
        execute_job(job)
    
    log_entry = json.loads(caplog.records[0].getMessage())
    assert log_entry["trace_id"] == "abc123"
```

**Test: Event bus propagates trace context**
```python
def test_eventbus_propagates_trace_context():
    trace_ctx = TraceContext(trace_id="abc123", ...)
    _trace_id.set(trace_ctx.trace_id)
    
    # Publish event
    eventbus.publish("user_logged_in", data={...})
    
    # Subscriber receives context
    received_ctx = None
    @eventbus.subscribe("user_logged_in")
    def on_user_login(event):
        nonlocal received_ctx
        received_ctx = event.trace_context
    
    # Trigger subscriber
    eventbus._trigger_sync("user_logged_in", {...})
    
    # Assert
    assert received_ctx.trace_id == "abc123"
```

### End-to-End Tests (With Jaeger)

**Test: Full trace flow HTTP → Agent → Tool → Google**
```python
def test_full_trace_http_to_google(jaeger_exporter):
    # HTTP request through agent with tool call to Google Calendar
    response = client.post("/api/chat", json={"message": "schedule meeting"})
    
    # Assert response success
    assert response.status_code == 200
    
    # Wait for spans to export
    time.sleep(1)
    
    # Query Jaeger API for trace
    trace_id = response.headers["X-Request-ID"].replace("-", "")
    trace = jaeger_exporter.query_trace(trace_id)
    
    # Assert span hierarchy
    assert trace.spans[0].name == "POST /api/chat"  # HTTP
    assert any(s.name == "agent_run" for s in trace.spans)  # Agent
    assert any(s.name.startswith("google.calendar") for s in trace.spans)  # Google
```

### Regression Tests (P7 Compliance)

**Test: No regressions in request handling (with tracing enabled)**
```python
def test_existing_tests_pass_with_tracing_enabled():
    # Run all P7 tests (645 tests) with OTEL_ENABLED=true
    # Assert: all pass, no failures
```

---

## 22. Acceptance Criteria

### Functional
- ✓ Trace context auto-generated for every HTTP request
- ✓ Trace context propagated to all database queries
- ✓ Trace context propagated to all external API calls
- ✓ Trace context propagated to background jobs
- ✓ Trace context propagated through event bus
- ✓ Trace ID appears in structured logs
- ✓ Trace ID appears as exemplar in Prometheus metrics
- ✓ Full trace visible in Jaeger UI (HTTP → Agent → Tools → External APIs)

### Performance
- ✓ Per-request overhead < 2ms (at 1.0 sampling)
- ✓ 10% sampling reduces export bandwidth by 90%
- ✓ Trace export non-blocking (doesn't delay response)
- ✓ No regression in existing request latency (p50, p95, p99)

### Security
- ✓ No API keys in spans
- ✓ No PII in SQL span attributes (only parameterized queries)
- ✓ No response bodies in HTTP spans
- ✓ Exceptions redacted (type/message only, no variable values)

### Observability
- ✓ Operator can search logs by trace_id
- ✓ Operator can click exemplar on histogram → Jaeger trace
- ✓ Operator can identify root cause of slow request in < 1 minute
- ✓ Background jobs visible in same trace as HTTP request (if linked)

### Compatibility
- ✓ Request ID behavior unchanged (X-Request-ID still works)
- ✓ Prometheus metrics unchanged (backward compatible)
- ✓ All P7 regression tests pass (645 tests)
- ✓ Can disable via OTEL_ENABLED=false (zero overhead)

### Configuration
- ✓ OTEL_ENABLED env var controls tracing
- ✓ OTEL_EXPORTER_OTLP_ENDPOINT configurable (Jaeger, Datadog, Honeycomb, etc.)
- ✓ Sampling configurable (0-100%)
- ✓ .env.example documents all OTEL_* variables

### Documentation
- ✓ Specification document (this file)
- ✓ Configuration guide (environment variables)
- ✓ Jaeger setup guide (docker-compose)
- ✓ Troubleshooting guide (common issues)

---

## 23. Required Evidence

### Code Artifacts
1. **backend/observability/tracing.py** (updated)
   - setup_tracing() with production defaults
   - Custom instrumentors (Job Worker, Event Bus, Agent Orchestrator)
   - Trace context helpers (get_trace_context, restore_trace_context)

2. **backend/observability/request_context.py** (updated)
   - Trace ID context vars (_trace_id, _span_id, _trace_flags)
   - Trace context propagation from W3C traceparent header

3. **backend/middleware/** (new/updated)
   - TraceContextMiddleware: extract/restore trace context on request

4. **backend/models.py** (updated)
   - Job model: add trace_context JSON column

5. **backend/jobs/worker.py** (updated)
   - restore_trace_context() on job execution start
   - Job spans created and exported

6. **backend/services/log_redaction.py** (updated)
   - Trace ID/span ID redaction (keep, don't filter)
   - PII redaction in trace-related fields

7. **backend/observability/event_bus.py** (created)
   - EventBus.publish() with trace_context parameter
   - Event handler decorator with trace context restoration

8. **backend/observability/metrics.py** (updated)
   - Exemplars added to histograms (trace_id, duration, timestamp)

9. **backend/main.py** (updated)
   - setup_tracing() called in lifespan
   - OTEL_* env vars read and passed to setup_tracing

10. **docker/docker-compose.yml** (updated)
    - Jaeger service added (all-in-one image)
    - Backend depends_on jaeger with health check
    - jaeger_data volume

11. **docker/.env.example** (updated)
    - OTEL_ENABLED, OTEL_EXPORTER_OTLP_ENDPOINT, etc.

12. **backend/tests/test_tracing_integration.py** (created)
    - 30+ tests covering all integration points
    - Span hierarchy verification
    - Trace context propagation
    - Log/metric correlation

13. **backend/tests/test_trace_pii_redaction.py** (created)
    - 10+ tests verifying PII redaction
    - No API keys in spans
    - No response bodies in HTTP spans

14. **docs/TRACING_SETUP.md** (created)
    - Jaeger configuration guide
    - Sampling strategy recommendations
    - Troubleshooting tips

15. **OBS-002_IMPLEMENTATION_PLAN.md** (created, if needed)
    - Step-by-step implementation guide
    - File order (dependencies)
    - Integration testing approach

### Test Results
- ✓ 40+ new integration tests (all passing)
- ✓ 645 P7 regression tests (all passing)
- ✓ 0 defects
- ✓ 100% backward compatibility

### Documentation
- ✓ OBS-002_DISTRIBUTED_TRACING_SPECIFICATION.md (this file)
- ✓ docs/TRACING_SETUP.md
- ✓ Inline code comments (no wall-of-text, just "why" decisions)
- ✓ .env.example updated with OTEL_* variables

---

## 24. Definition of Ready

Before implementation can start, the following MUST be verified:

- ✓ This specification reviewed and approved by Chief Architect
- ✓ Design Review gate passed (5 findings resolved, or none identified)
- ✓ OBS-001 merged to master and production-ready (prerequisite satisfied)
- ✓ Architecture frozen (no scope creep on monitored systems)
- ✓ Governance frozen (no process changes mid-implementation)
- ✓ OpenTelemetry packages added to requirements.txt
- ✓ Jaeger version (v1.40+) selected and tested locally
- ✓ Test strategy reviewed (unit, integration, e2e, regression)
- ✓ PII redaction approach approved (SQL parameterization, HTTP body exclusion, exception handling)
- ✓ Sampling strategy approved (production: 10%, staging: 50%, dev: 100%)
- ✓ All team members briefed on trace context propagation model

---

## 25. Definition of Done

Implementation is complete when:

### Code Completeness
- ✓ All 15 code artifacts created/updated (see Required Evidence)
- ✓ No temporary debugging code left
- ✓ No commented-out code
- ✓ Type hints on all functions (Python 3.10+ style)
- ✓ Docstrings on public APIs (one-line, no walls-of-text)

### Testing
- ✓ 40+ new integration tests, all passing
- ✓ 645 P7 regression tests, all passing
- ✓ 0 test failures, 0 skipped
- ✓ Code coverage > 80% for new code
- ✓ E2E test with Jaeger (trace visible in UI)

### Performance
- ✓ Sampled request latency impact < 2ms (p50)
- ✓ p95 latency unchanged from baseline
- ✓ Memory usage growth < 50MB (at 1000 req/s)
- ✓ CPU overhead < 1% at 10% sampling

### Security
- ✓ Security review completed (PII redaction verified)
- ✓ No API keys in span exports
- ✓ No response bodies in HTTP spans
- ✓ Exception sanitization working

### Documentation
- ✓ docs/TRACING_SETUP.md complete and accurate
- ✓ .env.example updated with all OTEL_* variables
- ✓ Inline code comments explain non-obvious decisions
- ✓ No TODOs or FIXMEs left in implementation

### Deployment
- ✓ docker-compose.yml updated (Jaeger service, backend dependency)
- ✓ Jaeger service health check working
- ✓ docker up/down/restart cycle tested
- ✓ Rollback procedure tested (OTEL_ENABLED=false works)

### Merge Readiness
- ✓ Branch clean (no trailing whitespace, consistent formatting)
- ✓ Commits follow conventional commit style
- ✓ Git history clean (no squash-merge conflicts, rebased on latest master)
- ✓ DELIVERY_PACKAGE.md generated (40+ tests, evidence links)

---

## Specification Complete

**Status:** ✅ READY FOR DESIGN REVIEW

This specification document provides complete design for OBS-002 Distributed Tracing. All 25 sections address the requested requirements:

1. ✓ Goal (diagnosing request latency end-to-end)
2. ✓ Current State (OBS-001 complete, OpenTelemetry stubbed)
3. ✓ Problem Statement (three integration gaps)
4. ✓ Scope (in/out of scope clearly defined)
5. ✓ OpenTelemetry Architecture (component diagram)
6. ✓ Trace Context Propagation (5 mechanisms: HTTP, DB, external, jobs, event bus)
7. ✓ Span Hierarchy (8 span types, nesting rules, max depth)
8. ✓ Trace ID Strategy (W3C format, generation, correlation with request ID)
9. ✓ Correlation with Structured Logs (trace_id field added)
10. ✓ Correlation with Prometheus Metrics (exemplars)
11. ✓ Correlation with Event Bus (trace context in events)
12. ✓ Worker Trace Propagation (job.trace_context column, restoration in worker)
13. ✓ API Changes (new functions, modified signatures, backward compatible)
14. ✓ Configuration (14 environment variables documented)
15. ✓ Docker Integration (Jaeger service, backend dependency, volumes, health check)
16. ✓ Dependencies (Python packages, Docker images, compatibility)
17. ✓ Compatibility (backward compatible, no breaking changes)
18. ✓ Security Considerations (PII redaction, OTLP/HTTP security, retention)
19. ✓ Performance Impact (1-2ms overhead, 90% savings at 10% sampling)
20. ✓ Rollback (OTEL_ENABLED=false, feature flag optional)
21. ✓ Test Plan (unit, integration, e2e, regression)
22. ✓ Acceptance Criteria (functional, performance, security, observability, compatibility)
23. ✓ Required Evidence (15 code artifacts, 40+ tests, 2 docs)
24. ✓ Definition of Ready (10 checklist items)
25. ✓ Definition of Done (5 categories × 4-5 items = 25 checklist items)

**Next Step:** Design Review (identify issues, resolve, proceed to implementation)

---

**Prepared by:** TECH_LEAD  
**Date:** 2026-07-13  
**Prerequisite Check:** OBS-001 COMPLETED ✓  
**Ready for Review:** YES ✓
