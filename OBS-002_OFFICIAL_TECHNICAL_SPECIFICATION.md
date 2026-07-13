# OBS-002 — Official Technical Specification

**Distributed Tracing Integration with Monitoring Stack**

**Status:** SPECIFICATION  
**Date:** 2026-07-13  
**Owner:** TECH_LEAD  
**Prerequisite:** OBS-001 COMPLETED ✓  
**Architecture:** FROZEN  
**Governance:** FROZEN  

---

## 1. Goal

Enable end-to-end visibility of request execution across all layers:
- HTTP request entry → agent execution → database queries → external API calls → response
- Correlate traces with structured logs (via trace ID)
- Correlate traces with Prometheus metrics (via exemplars in histograms)
- Diagnose latency bottlenecks and failures within 1-2 minutes

---

## 2. Current State

**OBS-001 Monitoring Stack (Available)**
- Prometheus: metrics collection, 15s scrape interval, 15d+15GB retention
- Alertmanager: routing tree (critical/warning), webhook/email receivers
- Grafana: 5 dashboards (system-health, agent-performance, job-queue, whatsapp, security)

**Existing Observability (Partial)**
- Request ID middleware: X-Request-ID header (UUID4), stored in contextvar
- Structured JSON logging: request_id stamped on every log entry
- Prometheus metrics: HTTP, agent, job, WhatsApp counters/histograms (no trace linking)
- OpenTelemetry packages: installed but disabled by default (OTEL_ENABLED=false)
- OTel auto-instrumentation: FastAPI, SQLAlchemy, httpx (stub, not enabled)

**Missing**
- Active distributed tracing (OTEL_ENABLED=true in production)
- Trace context propagation through job workers
- Trace context propagation through event bus
- Trace ID in structured logs (separate from request_id)
- Trace ID in Prometheus metrics (exemplars)
- Trace correlation with Grafana dashboards

---

## 3. Problem Statement

**Three Observability Gaps:**

1. **Traces isolated from each other**
   - Request flows through HTTP → agent → tools → database → external API
   - Each step auto-instrumented separately
   - No single trace connecting all steps
   - Operator cannot answer: "Which step was slowest?"

2. **Three observation pillars don't correlate**
   - Same request appears in: traces, logs, metrics
   - But no common ID linking them
   - Debugging requires manual search in 3 systems
   - Root cause analysis takes 15-20 minutes (10x too slow)

3. **Background operations invisible in traces**
   - Job worker executions have no trace context
   - Event bus publishes/subscribes without trace linking
   - Autonomous/delayed operations lose trace chain
   - Operator cannot correlate worker activity with original request

**Impact:** Production incident debugging is slow and manual-heavy.

---

## 4. Scope

**In Scope**
- Production-grade OpenTelemetry integration (always-on)
- Trace context propagation: HTTP, database, external APIs, jobs, event bus
- Trace ID generation and correlation with request ID
- Span hierarchy and parent-child relationships
- Integration of traces with OBS-001 (logs + metrics correlation)
- Jaeger collector as optional backend (for UI, export, retention)
- Configuration via environment variables
- Security: PII redaction in spans
- Performance: sampling strategy for cost control
- Rollback: zero-impact disable mechanism
- Testing: integration and end-to-end trace validation

**Out of Scope**
- Trace visualization UI (use Jaeger, Datadog, Honeycomb UI)
- Frontend/JavaScript tracing
- Custom span creation in business logic (auto-instrumentation only)
- APM alerting (future, OBS-003)
- Cost allocation by trace
- OpenTelemetry Collector (use OTLP/HTTP direct to backend)

---

## 5. Out of Scope

- Distributed tracing for frontend applications
- Manual span instrumentation in business logic
- Trace-based alerting and anomaly detection
- Cost optimization algorithms based on traces
- Custom exporters (use OTLP/HTTP only)
- Trace data federation across multiple services
- Real-time trace ingestion into Prometheus (exemplars only)

---

## 6. Trace Architecture

```
┌─────────────────────────────────────┐
│  Dario OS Backend (Instrumented)    │
│  - FastAPI (HTTP entry point)       │
│  - SQLAlchemy (database queries)    │
│  - httpx (external API calls)       │
│  - Job Worker (background jobs)     │
│  - Event Bus (async publish/sub)    │
└─────────────────────────────────────┘
           ↓ OTLP/HTTP (spans)
┌─────────────────────────────────────┐
│  OpenTelemetry SDK                  │
│  - TracerProvider (resource + config) │
│  - BatchSpanProcessor (async export)  │
│  - W3C TraceContext Propagator      │
└─────────────────────────────────────┘
           ↓ OTLP/HTTP protocol
┌─────────────────────────────────────┐
│  Trace Backend (Optional)            │
│  - Jaeger Collector (docker svc)    │
│  - Or: Datadog, Honeycomb, etc.     │
│  - Storage: local or remote         │
└─────────────────────────────────────┘
```

---

## 7. OpenTelemetry Strategy

**Components**
- TracerProvider: one global instance, resource = service name + environment
- Sampler: probabilistic (configurable rate: 0-100%)
- SpanProcessor: BatchSpanProcessor (async, 1024 spans/batch or 5s timeout)
- Exporter: OTLPSpanExporter (OTLP/HTTP protocol)
- Propagator: W3CTraceContextPropagator (HTTP traceparent header)

**Instrumentors (Auto-Instrumentation)**
- FastAPIInstrumentor: one span per HTTP request
- SQLAlchemyInstrumentor: one span per DB query
- HTTPXClientInstrumentor: one span per external API call
- Custom: Job Worker (one span per job execution)
- Custom: Event Bus (one span per publish/subscribe)
- Custom: Agent Orchestrator (one span per agent run)

**Disable Mechanism**
- Single env var: OTEL_ENABLED=false → zero overhead, no span creation

---

## 8. Trace Context Propagation

**Mechanism: W3C Trace Context (RFC 9110)**
```
traceparent: 00-{trace_id}-{span_id}-{trace_flags}
  trace_id:    32 hex chars (128 bit)
  span_id:     16 hex chars (64 bit)
  trace_flags: "01" (sampled) or "00" (not sampled)
```

**Five Propagation Paths**

1. **HTTP (Inbound Request)**
   - Extract traceparent header → contextvar (if present)
   - If missing: generate new trace_id (UUID4)
   - Echo trace_id back in X-Request-ID response header

2. **Database Queries**
   - SQLAlchemy reads contextvar trace_id
   - Creates child span (same trace_id, new span_id)
   - Parent span_id captured in span context

3. **External API Calls**
   - httpx reads contextvar trace_id
   - Adds traceparent header to outbound request
   - Creates child span with API response status

4. **Background Jobs**
   - HTTP enqueue stores trace_id in job metadata
   - Worker restores trace_id to contextvar on startup
   - Job execution linked to original request trace

5. **Event Bus**
   - Publish captures trace context in event envelope
   - Subscribe restores trace context before handler
   - Handler execution linked to publisher trace

---

## 9. Trace ID Generation

**Format: W3C Standard (32 hex characters)**
```
trace_id = UUID4 → hex-encoded
  Example: "550e8400-e29b-41d4-a716-446655440000" → "550e8400e29b41d4a716446655440000"
```

**Generation Rules**
- New HTTP request (no traceparent header): generate UUID4 → hex encode
- Existing traceparent header: extract trace_id
- Invalid header: generate new trace_id
- Job/Event: inherit parent request trace_id, generate new span_id

**Correlation with Request ID**
```
Request ID (existing): 550e8400-e29b-41d4-a716-446655440000 (UUID4)
Trace ID (new):       550e8400e29b41d4a716446655440000 (same UUID, hex format)
Relationship:         1:1 (one trace per request)
```

---

## 10. Span Hierarchy

**Eight Span Types**

| Span Type | Parent | Attributes | Child Spans |
|-----------|--------|------------|------------|
| HTTP Request | (root) | method, path, status, duration_ms | SQLAlchemy, Agent, HTTPx, Event Publish |
| SQLAlchemy Query | HTTP, Agent, Tool, Job | db, statement, duration_ms | (leaf) |
| Agent Run | HTTP | agent_name, planner_duration, executor_duration | Tool Call, SQLAlchemy, HTTPx |
| Tool Call | Agent | tool_name, result_status, duration_ms | HTTPx, SQLAlchemy |
| HTTPx (external API) | HTTP, Agent, Tool, Job | method, url, status, duration_ms | (leaf) |
| Job Execution | (root in worker) | job_name, job_id, parent_request_id, duration_ms | SQLAlchemy, Agent, HTTPx, Event |
| Event Publish | HTTP, Job | event_name, event_id, subscriber_count | Event Subscribe |
| Event Subscribe | Event Publish | event_name, handler_name, duration_ms | Agent, SQLAlchemy, HTTPx |

---

## 11. Parent / Child Relationships

**Nesting Rules**
```
HTTP Request (root)
  ├─ SQLAlchemy (direct child)
  ├─ Agent Run (direct child)
  │   ├─ Tool Call (child of Agent)
  │   │   ├─ HTTPx (child of Tool)
  │   │   ├─ SQLAlchemy (child of Tool)
  │   │   └─ Tool Call (nested Tool)
  │   ├─ SQLAlchemy (child of Agent)
  │   └─ HTTPx (child of Agent)
  ├─ HTTPx (direct child)
  └─ Event Publish (direct child)
      └─ Event Subscribe (child of Event)
          ├─ Agent Run (child of Subscriber)
          ├─ SQLAlchemy (child of Subscriber)
          └─ HTTPx (child of Subscriber)

Job Execution (root in worker process)
  ├─ SQLAlchemy (direct child)
  ├─ Agent Run (direct child)
  ├─ HTTPx (direct child)
  └─ Event (direct child)
```

**Constraints**
- Max nesting depth: 10 (prevent stack overflow)
- One root span per request or job
- Child span inherits parent's trace_id
- Child span generates new span_id

---

## 12. HTTP Request Tracing

**Entry Point: RequestIDMiddleware**
```python
# Request arrives
GET /api/chat?message=hello
  Header: traceparent: 00-{trace_id}-{span_id}-01  (optional)

# Middleware extracts/generates trace_id
if traceparent present:
    trace_id = extract_trace_id(traceparent)
else:
    trace_id = generate_trace_id()  # UUID4 → hex

# Store in contextvar for entire request
_trace_id.set(trace_id)
_span_id.set(new_span_id)
_trace_flags.set("01")  # sampled

# FastAPIInstrumentor creates HTTP span
[HTTP Span] method=GET, path=/api/chat, status=200, duration_ms=85

# Response echoes trace_id
Response Header: X-Request-ID: 550e8400e29b41d4a716446655440000
```

---

## 13. Background Worker Tracing

**Job Enqueue (in HTTP Request)**
```python
# Capture trace context
trace_context = {
    "trace_id": _trace_id.get(),
    "span_id": _span_id.get(),
    "trace_flags": _trace_flags.get()
}

# Store in job row (new JSON column)
job_queue.enqueue(
    job_name="send_email",
    recipient="user@example.com",
    trace_context=trace_context  # NEW
)
```

**Job Execution (in Worker Process)**
```python
# Dequeue job
job = job_queue.dequeue()

# Restore trace context before execution
restore_trace_context(job.trace_context)
_trace_id.set(job.trace_context["trace_id"])  # Same as HTTP request

# Job execution creates root span (same trace_id)
[Job Execution Span] job_name=send_email, parent_request_id=550e8400...

# All child spans (SQLAlchemy, HTTPx) linked to original HTTP trace
[Job Execution Span]
  └─ [SQLAlchemy Span] (same trace_id)
  └─ [HTTPx Span] (same trace_id)
```

---

## 14. Event Bus Trace Propagation

**Event Publish (in HTTP Request or Job)**
```python
# Capture trace context
trace_context = get_trace_context()  # {trace_id, span_id, trace_flags}

# Publish event with context
eventbus.publish(
    event_name="user_logged_in",
    data={...},
    trace_context=trace_context  # NEW (or auto-captured if None)
)

# Span created for publish
[Event Publish Span] event_name=user_logged_in, event_id=abc123
```

**Event Subscribe (Async Handler)**
```python
# Event handler receives event with trace_context
@eventbus.subscribe("user_logged_in")
async def on_user_login(event: Event):
    # Restore trace context (same as publisher)
    restore_trace_context(event.trace_context)
    
    # Handler execution linked to publisher's trace
    # All spans (agent, db, api) have same trace_id
    
    # Span created for subscriber
    [Event Subscribe Span] event_name=user_logged_in, handler=on_user_login
        └─ [Agent Run Span]
        └─ [SQLAlchemy Span]
```

---

## 15. Database Query Instrumentation

**SQLAlchemy Auto-Instrumentation**
```python
# In HTTP request or job context
from database.session import engine

# SQLAlchemyInstrumentor.instrument(engine)
# → Every query automatically creates a span

# Example query
user = db.query(User).filter(User.id == 123).first()

# Span created
[SQLAlchemy Span]
  parent_span_id: {current_http_span_id}
  attributes:
    - db.system: postgresql
    - db.name: darioos
    - db.statement: "SELECT * FROM users WHERE id = %s"  (parameterized)
    - db.duration_ms: 12
```

**Span Attributes**
- `db.system`: postgresql, mysql, sqlite
- `db.name`: database name (darioos)
- `db.statement`: SQL query (parameters omitted for security)
- `db.rows_affected`: number of rows
- `exception`: error message (if query failed)

---

## 16. External API Instrumentation

**httpx Auto-Instrumentation**
```python
# In HTTP request or job context
import httpx

# HTTPXClientInstrumentor.instrument()
# → Every outbound API call automatically creates a span

# Example: call Google Calendar API
async with httpx.AsyncClient() as client:
    response = await client.get(
        "https://www.googleapis.com/calendar/v3/events",
        headers={"Authorization": "Bearer ..."}
    )

# Span created
[HTTPx Span]
  parent_span_id: {current_agent_span_id}
  attributes:
    - http.method: GET
    - http.url: https://www.googleapis.com/calendar/v3/events
    - http.status_code: 200
    - http.duration_ms: 245
```

**Span Attributes**
- `http.method`: GET, POST, PUT, DELETE
- `http.url`: full URL (no query parameters, no auth headers)
- `http.status_code`: 200, 401, 500, etc.
- `http.duration_ms`: latency
- `exception`: error message (if request failed)

---

## 17. Correlation with Structured Logs

**Log Format (OBS-001)**
```json
{
  "timestamp": "2026-07-13T12:00:00Z",
  "level": "info",
  "logger": "backend.agents",
  "message": "Agent completed",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Log Format (OBS-002 Enhanced)**
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

**Implementation**
- LogFilter reads contextvar _trace_id (same as request_id filter)
- Add trace_id, span_id, trace_flags to every log record
- JSON formatter includes new fields
- Operator searches logs by trace_id → all events in one trace visible
- Click trace_id → opens trace in Jaeger UI

---

## 18. Correlation with Prometheus Metrics

**Current Metrics (OBS-001)**
```
darioos_http_request_duration_seconds_bucket{method="POST",path="/api/chat",le="0.1"} 5
```

**Enhanced Metrics (OBS-002 with Exemplars)**
```
darioos_http_request_duration_seconds_bucket{method="POST",path="/api/chat",le="0.1"} 5
  exemplar: trace_id="550e8400e29b41d4a716446655440000", value=0.085s, timestamp=...

darioos_agent_runs_total{agent="planner",status="success"} 42
  exemplar: trace_id="550e8400e29b41d4a716446655440000", timestamp=...
```

**Implementation**
- Histogram spans record exemplar on completion
- OTel SDK exports exemplars in OTLP format
- Grafana displays trace link on histogram hover
- Click exemplar → opens Jaeger UI with that trace

**Dashboards (Grafana → Jaeger Flow)**
1. Operator sees high p95 latency on "POST /api/chat" histogram
2. Hovers bucket → exemplar list appears
3. Clicks exemplar → Jaeger UI opens with full trace
4. Identifies bottleneck (e.g., Google Calendar timeout)

---

## 19. Correlation with Grafana Dashboards

**System Health Dashboard Enhancement**
```
Current:  Request Volume, Error Rate, Response Latency, Backend Uptime
New:      Same panels + exemplars on Request Volume histogram

Usage:
  - Operator sees request volume spike
  - Clicks histogram bucket
  - Views exemplar (slowest request in bucket)
  - Clicks "View Trace" → Jaeger opens
  - Sees: agent planning 1.2s, tool call 0.8s, Google API timeout
```

**Agent Performance Dashboard Enhancement**
```
Current:  Agent Runs, Tool Invocations, Agent Timeouts, LLM Cost
New:      Same panels + exemplars on Agent Runs histogram

Usage:
  - Operator sees tool call failures spike
  - Clicks histogram → exemplar shows failed trace
  - Jaeger shows which tool failed and why (exception in span)
```

**Job Queue Dashboard Enhancement**
```
Current:  Queue Depth, Throughput, Success Rate, Processing Time
New:      Same panels + exemplars on Processing Time histogram

Usage:
  - Operator sees processing time spike
  - Clicks exemplar → Jaeger shows slow job trace
  - Identifies database query as bottleneck
```

---

## 20. Sampling Strategy

**Three Deployment Profiles**

| Environment | Sampler | Rate | Rationale |
|-------------|---------|------|-----------|
| Development | always_on | 100% | Debug all requests |
| Staging | probabilistic | 50% | Balance cost/visibility |
| Production | traceidratio | 10% | Minimize cost, 100 req/s sampled from 1000 |

**Configuration**
```bash
# Development
OTEL_TRACES_SAMPLER=always_on

# Staging
OTEL_TRACES_SAMPLER=probabilistic
OTEL_TRACES_SAMPLER_ARG=0.5  # 50%

# Production
OTEL_TRACES_SAMPLER=traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1  # 10%
```

**Cost Impact (1000 req/sec backend)**
- 100% sampling: 5,000 spans/sec → 500 KB/s bandwidth → 50 MB/day storage
- 10% sampling: 500 spans/sec → 50 KB/s bandwidth → 5 MB/day storage (90% savings)

**Sampling Transparency**
- Trace header includes trace_flags ("01" = sampled, "00" = not sampled)
- Backend respects sampler decision (not all traces exported)
- Logs always created (trace_id present even if span not exported)

---

## 21. Performance Impact

**Per-Request Overhead**

| Component | Overhead | Notes |
|-----------|----------|-------|
| Span creation | <1ms | In-memory, batched export |
| Log enrichment | <0.1ms | Filter + JSON update |
| Exemplar capture | <0.5ms | On histogram completion |
| Batch export | 0ms | Async, non-blocking |
| **Total** | **~1-2ms** | Per request (at 100% sampling) |

**At 10% Sampling (Production)**
- CPU overhead: ~0.5% (was ~5% at 100%)
- Memory overhead: 5 MB (was 50 MB)
- Network overhead: 50 KB/s (was 500 KB/s)
- **No performance regression: span export is non-blocking**

**Recommendations**
- Dev: 100% sampling (1-2ms overhead acceptable)
- Staging: 50% sampling (0.5-1ms overhead)
- Production: 10% sampling (0.1-0.2ms overhead)
- High-traffic endpoints: 1% or lower sampler_arg

---

## 22. Security Considerations

**PII Redaction**

| Data | Captured | Reason | Safe? |
|------|----------|--------|-------|
| SQL query (statement) | `SELECT * FROM users WHERE id = ?` | Parameters stripped | ✓ Yes |
| HTTP status/duration | `200, 245ms` | Metadata only | ✓ Yes |
| External API URL | `https://www.googleapis.com/calendar/v3/events` | Endpoint only | ✓ Yes |
| Response body | Not captured | Sensitive data | ✓ Yes |
| Auth headers | Not captured | Bearer tokens excluded | ✓ Yes |
| API keys | Not captured | Stripped during instrumentation | ✓ Yes |
| Exception message | `ValueError: Invalid input` | Type + message only | ✓ Yes |
| Exception stack trace | `file.py:123` | Stack trace (no variable values) | ✓ Yes |

**Mitigation Strategy**
1. SQLAlchemy: parameterized queries (no values in statement)
2. httpx: URL only, no response body or auth headers
3. Exceptions: type + message, no variable values
4. PII filtering: redaction on span export (optional)

**OTLP/HTTP Security**
- Optional TLS: set OTEL_EXPORTER_OTLP_CERTIFICATE
- Optional auth: set OTEL_EXPORTER_OTLP_HEADERS=Authorization:Bearer+{token}
- Network isolation: Jaeger on internal darioos network (not public)

**Data Retention**
- Jaeger default: 72 hours
- Production: configure Elasticsearch backend for longer retention
- Traces auto-delete after retention window
- No GDPR/compliance special handling needed (not PII-heavy)

---

## 23. Configuration Files

**Environment Variables (.env)**
```bash
# OBS-002: Distributed Tracing
OTEL_ENABLED=true                                    # Enable/disable entirely
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318       # OTLP/HTTP backend
OTEL_SERVICE_NAME=darioos                             # Service name in traces
OTEL_RESOURCE_ATTRIBUTES=environment=production      # Additional tags
OTEL_TRACES_SAMPLER=traceidratio                     # Sampling strategy
OTEL_TRACES_SAMPLER_ARG=0.1                          # Sample 10%
OTEL_BATCH_SIZE=1024                                  # Spans per batch
OTEL_BATCH_TIMEOUT_MS=5000                            # Batch timeout (ms)
OTEL_EXPORTER_OTLP_CERTIFICATE=/path/to/ca.pem      # TLS cert (optional)
OTEL_EXPORTER_OTLP_HEADERS=Authorization:Bearer+...  # Auth headers (optional)
```

**docker-compose.yml Addition**
```yaml
jaeger:
  image: jaegertracing/all-in-one:latest
  ports:
    - "16686:16686"      # UI
    - "4318:4318"        # OTLP/HTTP receiver
  environment:
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

volumes:
  jaeger_data:
```

**Backend Service Update**
```yaml
backend:
  environment:
    OTEL_ENABLED: "${OTEL_ENABLED:-true}"
    OTEL_EXPORTER_OTLP_ENDPOINT: "http://jaeger:4318"
    OTEL_SERVICE_NAME: "darioos"
  depends_on:
    jaeger:
      condition: service_healthy
```

---

## 24. Docker Integration

**Jaeger All-in-One Service**
```yaml
jaeger:
  image: jaegertracing/all-in-one:latest
  container_name: darioos-jaeger
  ports:
    - "16686:16686"  # Web UI (http://localhost:16686 in dev)
    - "4318:4318"    # OTLP/HTTP receiver (backend connects here)
  environment:
    COLLECTOR_OTLP_ENABLED: "true"
    MEMORY_MAX_TRACES: 10000          # Max traces in memory
  volumes:
    - jaeger_data:/badger             # Persistent storage
  networks:
    - darioos
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:14269/status"]
    interval: 10s
    timeout: 5s
    retries: 3
    start_period: 10s
```

**Volume**
```yaml
volumes:
  jaeger_data:  # Badger DB storage (traces, spans, indices)
```

**Network**
```yaml
networks:
  darioos:      # Both jaeger and backend on same internal network
    driver: bridge
```

**Backend Dependency**
```yaml
backend:
  depends_on:
    prometheus:
      condition: service_healthy
    jaeger:                              # NEW
      condition: service_healthy
```

**Health Check**
```yaml
jaeger:
  healthcheck:
    test: curl -f http://localhost:14269/status || exit 1
    interval: 10s
    timeout: 5s
    retries: 3
    start_period: 10s
```

---

## 25. Dependencies

**Python Packages (New)**
```
opentelemetry-api==1.20.0
opentelemetry-sdk==1.20.0
opentelemetry-exporter-otlp==1.20.0
opentelemetry-instrumentation-fastapi==0.41b0
opentelemetry-instrumentation-sqlalchemy==0.41b0
opentelemetry-instrumentation-httpx==0.41b0
```

**Existing Packages (No Changes)**
- fastapi ≥ 0.95.0
- sqlalchemy ≥ 1.4.0
- httpx ≥ 0.23.0
- prometheus_client ≥ 0.16.0 (OBS-001)

**Docker Images**
- jaegertracing/all-in-one:latest (v1.40+)

**System Requirements**
- Python ≥ 3.8 (OTel requirement)
- 50-100 MB additional disk (Jaeger storage)

---

## 26. Compatibility

**Backward Compatibility: 100%**
- Request ID behavior unchanged (X-Request-ID still works)
- Prometheus metrics unchanged (exemplars are additive)
- Logging unchanged (trace_id field added, existing fields preserved)
- All API changes are additive (new parameters optional)

**No Breaking Changes**
- Existing code continues to work
- Trace context propagation automatic (no manual threading)
- Sampling doesn't break logging (trace_id always in logs)
- Disabling tracing (OTEL_ENABLED=false) has zero overhead

**Version Support**
- OpenTelemetry: stable v1.20+ (no breaking changes planned)
- Jaeger: v1.40+ (supports OTLP/HTTP)
- Prometheus: v2.45+ (already in OBS-001)

---

## 27. Rollback Strategy

**Immediate Disable (No Restart)**
```bash
# Single env var
OTEL_ENABLED=false

# Effect:
# - No spans created
# - No network calls to Jaeger
# - Zero overhead
# - Logs unchanged (trace_id field preserved)
# - Metrics unchanged (exemplars not captured)
```

**If Jaeger Fails**
- Backend continues normally (OTel export failure is non-blocking)
- Spans buffered in memory (up to memory limit)
- Export retries (exponential backoff)
- No request failures (telemetry-safe)

**Complete Rollback**
1. Set OTEL_ENABLED=false
2. Remove Jaeger service from docker-compose.yml
3. Remove OTEL_* env vars from .env
4. Restart backend
5. (Optional) Remove trace_context column from Job model

**Zero Data Loss**
- Job.trace_context column can be ignored (backward compatible)
- Existing logs/metrics remain unchanged
- No migration needed

---

## 28. Test Plan

**Unit Tests (15 tests)**
- get_trace_context() returns correct contextvar values
- restore_trace_context() restores contextvar
- Trace ID generation (UUID4 → hex encoding)
- Trace ID validation (reject invalid formats)
- Span context hierarchy (parent-child relationships)

**Integration Tests (25 tests)**
- HTTP request creates span (FastAPI)
- Database query creates nested span (SQLAlchemy)
- External API call creates nested span (httpx)
- Job execution inherits trace context
- Event publish/subscribe propagates trace context
- Trace ID in structured logs
- Trace ID in Prometheus exemplars

**End-to-End Tests (10 tests)**
- Full trace flow: HTTP → Agent → Tool → Google Calendar → Response
- Jaeger UI displays complete trace
- Grafana exemplar links to correct trace
- Job trace correlates with original HTTP trace
- Event subscriber trace linked to publisher

**Regression Tests (645 tests, OBS-001 baseline)**
- All P7 security tests pass (645 tests)
- No latency regression (p50, p95, p99 unchanged)
- No memory regression
- No CPU regression

**Total: 695 tests**

---

## 29. Acceptance Criteria

**Functional**
- ✓ Trace context auto-generated for every HTTP request
- ✓ Trace context propagated to database queries (nested spans)
- ✓ Trace context propagated to external API calls (nested spans)
- ✓ Trace context propagated to background jobs (inherited from enqueue)
- ✓ Trace context propagated through event bus (envelope + restore)
- ✓ Full trace visible in Jaeger UI (all 8 span types present)
- ✓ Trace ID appears in structured logs (trace_id + span_id fields)
- ✓ Trace ID appears as exemplar in Prometheus histograms

**Performance**
- ✓ Per-request overhead < 2ms (at 100% sampling)
- ✓ 10% sampling reduces export bandwidth 90%
- ✓ Trace export non-blocking (doesn't delay response)
- ✓ No regression: p50, p95, p99 latency unchanged

**Security**
- ✓ No API keys in spans
- ✓ No PII in SQL statements (parameterized only)
- ✓ No response bodies in HTTP spans
- ✓ Exceptions sanitized (type + message, no variable values)

**Observability**
- ✓ Operator can search logs by trace_id
- ✓ Operator can click exemplar → Jaeger (full trace visible)
- ✓ Operator can identify bottleneck in < 2 minutes
- ✓ Background jobs visible in same trace as HTTP request

**Compatibility**
- ✓ Request ID behavior unchanged
- ✓ Prometheus metrics backward compatible
- ✓ All 645 P7 regression tests pass
- ✓ Can disable via OTEL_ENABLED=false (zero overhead)

---

## 30. Required Evidence

**Code Artifacts (15)**
1. backend/observability/tracing.py (setup_tracing, context helpers)
2. backend/observability/request_context.py (trace_id contextvars)
3. backend/middleware/trace_context.py (TraceContextMiddleware)
4. backend/models.py (Job.trace_context column)
5. backend/jobs/worker.py (restore_trace_context on job execution)
6. backend/services/event_bus.py (trace_context in event envelope)
7. backend/main.py (setup_tracing called in lifespan)
8. docker/docker-compose.yml (Jaeger service)
9. docker/.env.example (OTEL_* variables)
10-14. (5 more instrumentor/integration files)
15. docs/TRACING_SETUP.md (configuration guide)

**Test Artifacts (50)**
- 15 unit tests (context, generation, validation)
- 25 integration tests (span hierarchy, propagation, correlation)
- 10 end-to-end tests (full traces in Jaeger)

**Test Results**
- 50 new tests: all passing
- 645 P7 regression tests: all passing
- Total: 695 passing, 0 failing

**Documentation Artifacts**
- OBS-002_OFFICIAL_TECHNICAL_SPECIFICATION.md (this file)
- docs/TRACING_SETUP.md (setup guide)
- Inline code comments (non-obvious decisions)

---

## 31. Definition of Ready

Before implementation starts:

- ✓ This specification reviewed and approved by Chief Architect
- ✓ Design Review gate passed (findings resolved or none identified)
- ✓ OBS-001 production-ready (prerequisite satisfied)
- ✓ Architecture frozen (scope locked)
- ✓ Governance frozen (process locked)
- ✓ OTel packages added to requirements.txt
- ✓ Jaeger v1.40+ selected and tested locally
- ✓ Test strategy reviewed (50 new + 645 regression)
- ✓ PII redaction approach approved
- ✓ Sampling strategy approved (dev/staging/prod rates)

---

## 32. Definition of Done

Implementation complete when:

**Code (15 artifacts)**
- ✓ All files created/updated
- ✓ No temporary code
- ✓ Type hints on all functions
- ✓ Docstrings on public APIs
- ✓ No TODOs or FIXMEs

**Testing (50 new + 645 regression)**
- ✓ All 50 new tests passing
- ✓ All 645 P7 regression tests passing
- ✓ Code coverage > 80% on new code
- ✓ E2E test: trace visible in Jaeger UI

**Performance**
- ✓ Per-request overhead < 2ms
- ✓ p95 latency unchanged from baseline
- ✓ Memory growth < 50MB
- ✓ CPU overhead < 1% (at 10% sampling)

**Security**
- ✓ Security review completed
- ✓ PII redaction verified
- ✓ No API keys exported
- ✓ Exception sanitization working

**Documentation**
- ✓ docs/TRACING_SETUP.md complete
- ✓ .env.example updated
- ✓ Inline comments explain decisions
- ✓ No documentation TODOs

**Deployment**
- ✓ docker-compose.yml updated
- ✓ Jaeger health check working
- ✓ docker up/down/restart cycle tested
- ✓ Rollback tested (OTEL_ENABLED=false works)

**Merge Readiness**
- ✓ Branch clean
- ✓ Commits follow conventional style
- ✓ Git history clean
- ✓ DELIVERY_PACKAGE.md generated

---

**OBS-002 Official Technical Specification — Complete**

**Status:** ✅ READY FOR DESIGN REVIEW

**Next Step:** Chief Architect review (approve or request changes)

---

**Prepared by:** TECH_LEAD  
**Date:** 2026-07-13  
**Prerequisite:** OBS-001 COMPLETED ✓
