# Infrastructure Validation Gate — OBS-002
## Pre-Production Infrastructure Validation

**Program**: OBS-002 (Distributed Tracing)  
**Gate**: INFRASTRUCTURE_VALIDATION  
**Owner**: Tech Lead  
**Date**: 2026-07-13  
**Status**: ⏳ PENDING VALIDATION  

---

## Infrastructure Validation Scope

Per CADR-007 (Chief Architect Decision Record #7), the following infrastructure components must be validated before production deployment:

### 1. Docker: Jaeger Service ✅ VERIFICATION READY

**Objective**: Verify Jaeger tracing backend can be deployed and responds to OTLP/HTTP requests

**Validation Steps**:
- [ ] Start Jaeger service via Docker: `docker run -d -p 16686:16686 -p 4317:4317 -p 4318:4318 jaeger/all-in-one:latest`
- [ ] Verify service startup: `docker ps | grep jaeger`
- [ ] Test health check: `curl http://localhost:16686/health`
- [ ] Expected response: HTTP 200 with JSON health status
- [ ] Verify port 4318 (OTLP/HTTP): `curl http://localhost:4318/v1/health` (expects 200)
- [ ] Jaeger UI accessible: `http://localhost:16686`
- [ ] UI loads without errors
- [ ] Jaeger ready for span ingestion

**Evidence to Capture**:
- Docker container ID
- Startup logs
- Health check response
- Jaeger UI screenshot
- Port connectivity confirmation

---

### 2. Networking: OTLP/HTTP Endpoint ✅ VERIFICATION READY

**Objective**: Verify application can reach Jaeger OTLP/HTTP endpoint

**Validation Steps**:
- [ ] Set `OTEL_ENABLED=true` in environment
- [ ] Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` (or production URL)
- [ ] Start application: `docker run -e OTEL_ENABLED=true -e OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318 app:latest`
- [ ] Application startup logs should show tracing initialized
- [ ] Generate a request: `curl http://localhost:8000/api/health`
- [ ] Wait 2-3 seconds for span export
- [ ] Check Jaeger UI for traces: http://localhost:16686/search
- [ ] Service name should appear in "Service" dropdown
- [ ] At least one trace visible (health check request)
- [ ] Span details show HTTP method, path, duration
- [ ] Trace ID format: 32 hex characters (W3C format)

**Expected Behavior**:
```
OTEL Tracing initialized
Service: dario-os
Spans exporting to: http://localhost:4318
Trace endpoint: http://localhost:16686
```

**Evidence to Capture**:
- Application startup log (OTEL initialization)
- Jaeger UI service list screenshot
- Trace example (trace ID, spans, duration)
- Network connectivity confirmation

---

### 3. Prometheus: Metrics Collection ✅ VERIFICATION READY

**Objective**: Verify Prometheus can scrape operational metrics from application

**Validation Steps**:
- [ ] Start Prometheus: `docker run -d -p 9090:9090 -v prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus`
- [ ] Configure Prometheus to scrape application `/metrics` endpoint
  - Target: `http://localhost:8000/metrics` (or application host:port)
  - Scrape interval: 15s
- [ ] Verify metrics endpoint: `curl http://localhost:8000/metrics | head -20`
- [ ] Check for OTel metrics in response:
  - `otel_span_exports_total` (counter, type: gauge or counter)
  - `otel_spans_dropped_total` (counter)
  - `otel_sampling_rate` (gauge, 0.0-1.0)
  - `otel_exemplars_registered_total` (counter)
- [ ] Generate traffic (multiple requests): `for i in {1..10}; do curl http://localhost:8000/api/health; done`
- [ ] Wait for next Prometheus scrape
- [ ] Verify metrics in Prometheus UI: http://localhost:9090
- [ ] Query: `otel_span_exports_total` — should show increasing values
- [ ] Query: `otel_sampling_rate` — should show current rate (0.0-1.0)
- [ ] Query: `otel_spans_dropped_total` — should match dropped span count

**Expected Metrics**:
```
# HELP otel_span_exports_total Total spans exported
# TYPE otel_span_exports_total gauge
otel_span_exports_total 10

# HELP otel_sampling_rate Current sampling rate
# TYPE otel_sampling_rate gauge
otel_sampling_rate 0.1

# HELP otel_exemplars_registered_total Total exemplars registered
# TYPE otel_exemplars_registered_total gauge
otel_exemplars_registered_total 3
```

**Evidence to Capture**:
- Prometheus configuration file
- Metrics endpoint output
- Prometheus UI graph (metrics over time)
- Metric values confirmation
- Exemplar samples in metrics

---

### 4. Grafana: Dashboard Import ✅ VERIFICATION READY

**Objective**: Verify Grafana can import and display OBS-002 tracing dashboard

**Validation Steps**:
- [ ] Start Grafana: `docker run -d -p 3000:3000 grafana/grafana:latest`
- [ ] Access Grafana UI: http://localhost:3000 (admin/admin)
- [ ] Add Prometheus data source:
  - URL: http://prometheus:9090
  - Test connection: should succeed
- [ ] Add Jaeger data source:
  - URL: http://jaeger:16686
  - Test connection: should succeed
- [ ] Import dashboard from `OBS-002_GRAFANA_DASHBOARD.json`:
  - Use Grafana "Dashboards" → "Import" → paste JSON
  - Select Prometheus and Jaeger data sources
- [ ] Dashboard should import without errors
- [ ] Verify 6 panels render:
  1. Trace Timeline (Jaeger)
  2. Log Correlation (Loki with trace links)
  3. Exemplar Panel (Prometheus exemplars)
  4. Sampling Rate (gauge)
  5. Span Export (bar gauge)
  6. Error Traces (Jaeger errors)
- [ ] Each panel should show data (not "No data" or errors)
- [ ] Sampling rate panel shows 0.0-1.0 gauge
- [ ] Span export shows exported vs dropped counts
- [ ] Exemplars show trace_id clickable links
- [ ] Dashboard time range: 1 hour (default)
- [ ] Refresh rate: 10 seconds

**Expected Dashboard State**:
```
✅ 6 panels visible
✅ All data sources connected
✅ Metrics flowing
✅ Traces flowing
✅ No error messages
✅ Dashboard responsive
```

**Evidence to Capture**:
- Grafana UI screenshot (dashboard loaded)
- Panel configuration verification
- Data source connectivity
- Dashboard JSON validated
- Exemplar links working

---

### 5. External Backends: Jaeger + Prometheus ✅ VERIFICATION READY

**Objective**: Verify production-grade deployments of Jaeger and Prometheus

**Validation Steps**:

#### Jaeger Production Validation:
- [ ] Jaeger deployed on production infrastructure
- [ ] Service health check passes: `/health`
- [ ] OTLP/HTTP endpoint responds (port 4318)
- [ ] Jaeger UI accessible and responsive
- [ ] Retention policy configured (e.g., 72 hours)
- [ ] Storage backend configured (Elasticsearch/Cassandra/BadgerDB)
- [ ] SSL/TLS enabled (if public endpoint)
- [ ] Authentication configured (if required)
- [ ] Logging enabled and monitored
- [ ] Resource limits set (CPU, memory)
- [ ] Backup/disaster recovery plan in place

#### Prometheus Production Validation:
- [ ] Prometheus deployed on production infrastructure
- [ ] Service health check passes
- [ ] Metrics endpoint accessible (port 9090)
- [ ] Scrape interval configured (recommend 15s)
- [ ] Retention policy configured (default 15 days)
- [ ] Storage backend configured and sized
- [ ] SSL/TLS enabled (if public endpoint)
- [ ] Authentication configured (if required)
- [ ] Alert rules defined and loaded
- [ ] Recording rules configured (if needed)
- [ ] Alertmanager integration verified
- [ ] Backup/disaster recovery plan in place

**Evidence to Capture**:
- Deployment manifests (Kubernetes, Docker Compose, etc.)
- Service health check results
- Endpoint connectivity verification
- Resource allocation confirmation
- Monitoring and alerting setup
- Backup procedures documented

---

### 6. Log Correlation: Trace ID in Logs ✅ VERIFICATION READY

**Objective**: Verify trace_id appears in all application logs

**Validation Steps**:
- [ ] Set `OTEL_ENABLED=true`
- [ ] Generate a request: `curl http://localhost:8000/api/health`
- [ ] Capture the response header `X-Request-ID` (contains trace_id)
- [ ] Check application logs for that trace_id
- [ ] Log format should show: `[request_id:trace_id]` for text logs
- [ ] For JSON logs, verify `trace_id` field present
- [ ] Generate multiple requests with different trace IDs
- [ ] Verify each log contains its corresponding trace_id
- [ ] Log-to-trace navigation: grep logs by trace_id to find all related logs
  - Example: `grep "abc123def456" app.log | grep -E "ERROR|WARN"`
- [ ] All logs for same trace should have identical trace_id
- [ ] Different traces should have different trace_ids

**Expected Log Format**:

Text:
```
2026-07-13 17:45:23,156 | INFO     | main | [req-123:abc123def456] | Health check OK
2026-07-13 17:45:23,157 | INFO     | main | [req-123:abc123def456] | Database query executed
```

JSON:
```json
{
  "timestamp": "2026-07-13T17:45:23.156Z",
  "level": "INFO",
  "logger": "main",
  "message": "Health check OK",
  "request_id": "req-123",
  "trace_id": "abc123def456"
}
```

**Evidence to Capture**:
- Application logs (text format sample)
- JSON logs (structured format sample)
- Grep results showing trace_id correlation
- Multiple log entries with same trace_id
- Trace to logs navigation example

---

### 7. End-to-End Trace Flow ✅ VERIFICATION READY

**Objective**: Verify complete trace flow from HTTP request through all system components

**Validation Steps**:
- [ ] Make HTTP request: `curl -v http://localhost:8000/api/health`
- [ ] Request creates root span in HTTP middleware
- [ ] If request contains SQL query:
  - [ ] SQLAlchemy creates child span for query
  - [ ] Span parent is HTTP request span
  - [ ] Query duration captured in span
- [ ] If request makes external API call:
  - [ ] httpx creates child span for call
  - [ ] traceparent header injected in request
  - [ ] Upstream service receives trace context
- [ ] If request creates background job:
  - [ ] Job Worker receives trace in payload
  - [ ] Job execution has child span
  - [ ] Trace preserved across async boundary
- [ ] If request publishes event:
  - [ ] Event Bus enriches payload with trace
  - [ ] Event handler receives trace context
  - [ ] Handler spans are children of event span
- [ ] All spans export to Jaeger within 2-3 seconds
- [ ] Jaeger shows complete trace tree
- [ ] Verify parent-child relationships
- [ ] Verify span durations add up correctly
- [ ] Verify trace ID consistent across all spans

**Expected Trace Structure**:
```
Trace: abc123def456
├─ Span: GET /api/health (HTTP)
│  ├─ Span: SELECT health (SQLAlchemy)
│  ├─ Span: POST http://external-api.com (httpx)
│  ├─ Span: job_worker:process_data (Job)
│  └─ Span: event_bus:on_health_checked (Event)
```

**Evidence to Capture**:
- Jaeger trace screenshot (tree view)
- Span details (parent-child relationships)
- Timeline view (span durations)
- Trace ID consistency verification
- All propagation mechanisms verified

---

### 8. Backward Compatibility: Tracing Disabled ✅ VERIFICATION READY

**Objective**: Verify application works correctly with tracing disabled

**Validation Steps**:
- [ ] Start application with `OTEL_ENABLED=false` (default)
- [ ] No startup errors
- [ ] Application functions normally
- [ ] No OTEL warnings in logs
- [ ] Requests complete successfully
- [ ] Response time reasonable (no tracing overhead)
- [ ] No span export errors
- [ ] Jaeger UI shows no new traces
- [ ] `/metrics` endpoint still works
- [ ] Application can be toggled to `OTEL_ENABLED=true` at runtime (reload config)
- [ ] Toggling on/off doesn't crash application

**Expected Behavior**:
- No performance degradation
- No errors or warnings
- All features work unchanged
- Tracing can be enabled later

**Evidence to Capture**:
- Startup log (OTEL disabled)
- Application behavior verification
- Performance metrics
- Metrics endpoint accessible
- Runtime toggle test results

---

### 9. Performance Validation ✅ VERIFICATION READY

**Objective**: Verify tracing has negligible performance impact

**Validation Steps**:
- [ ] Baseline test with `OTEL_ENABLED=false`:
  - [ ] Run load test: 100 requests/sec for 60 seconds
  - [ ] Measure: Response time (p50, p95, p99)
  - [ ] Measure: CPU usage (%)
  - [ ] Measure: Memory usage (MB)
  - [ ] Record baseline metrics
- [ ] Run with `OTEL_ENABLED=true`:
  - [ ] Same load test: 100 requests/sec for 60 seconds
  - [ ] Measure: Response time (p50, p95, p99)
  - [ ] Measure: CPU usage (%)
  - [ ] Measure: Memory usage (MB)
- [ ] Compare results:
  - [ ] Response time increase < 5% (target)
  - [ ] CPU increase < 10% (target)
  - [ ] Memory increase < 20MB (bounded exemplars)
- [ ] Verify sampling reduces load:
  - [ ] Test with `OTEL_SAMPLING=never` (no sampling)
  - [ ] Test with `OTEL_SAMPLING=fixed:0.1` (10% sampling)
  - [ ] Test with `OTEL_SAMPLING=error:0.05` (error sampling)
  - [ ] Verify load proportional to sampling rate

**Expected Results**:
```
Metric             | Disabled | Enabled (1.0)  | Delta  | Pass?
Response (p50)     | 50ms     | 51ms           | +2%    | ✅
Response (p95)     | 120ms    | 125ms          | +4%    | ✅
Response (p99)     | 200ms    | 210ms          | +5%    | ✅
CPU                | 25%      | 27%            | +8%    | ✅
Memory             | 150MB    | 160MB          | +6%    | ✅
```

**Evidence to Capture**:
- Load test configuration
- Performance metrics (baseline vs enabled)
- Graphs showing impact
- Sampling impact analysis
- Exemplar storage growth (should be bounded)

---

### 10. Security Validation ✅ VERIFICATION READY

**Objective**: Verify no secrets leaked in tracing data

**Validation Steps**:
- [ ] Make request with authorization header: `Authorization: Bearer secret-token-12345`
- [ ] Check Jaeger: Authorization header NOT in spans
- [ ] Check logs: Authorization header NOT logged
- [ ] Check metrics: No secrets in exemplar payload
- [ ] Make request with query params containing secrets
  - [ ] Example: `/api/search?api_key=sk-12345&password=secret`
  - [ ] Check Jaeger: URL logged WITHOUT secrets
  - [ ] Check logs: URL logged WITHOUT secrets
- [ ] Make request with SQL containing secrets
  - [ ] Example: `SELECT * FROM users WHERE password = 'super-secret'`
  - [ ] Check Jaeger: SQL query logged WITHOUT secrets
  - [ ] Check logs: SQL query logged WITHOUT secrets
- [ ] trace_id is not sensitive (safe to log, share, include in metrics)
- [ ] Verify OpenTelemetry attribute filtering is applied
- [ ] Verify log redaction is working
- [ ] Verify no database credentials in connection strings

**Expected Behavior**:
- No secrets in span attributes
- No secrets in logs
- No secrets in metrics
- trace_id safe to share
- Sensitive fields redacted

**Evidence to Capture**:
- Jaeger span with redacted attributes
- Log output showing redaction
- Security test results
- Attribute filtering configuration

---

## Validation Execution Plan

### Phase 1: Local Development (Immediate)
1. ✅ Jaeger Docker validation
2. ✅ OTLP/HTTP endpoint test
3. ✅ Trace flow verification
4. ✅ Backward compatibility check
5. ✅ Log correlation test

### Phase 2: Staging Environment (Before Production)
6. ✅ Prometheus metrics collection
7. ✅ Grafana dashboard import
8. ✅ Performance load testing
9. ✅ Security data validation
10. ✅ End-to-end trace flow

### Phase 3: Production Readiness (Final Gate)
- [ ] Production Jaeger deployment verified
- [ ] Production Prometheus deployment verified
- [ ] Production Grafana deployment verified
- [ ] All validation checkpoints passed
- [ ] Incident response plan in place
- [ ] Monitoring and alerting active

---

## Success Criteria

**All of the following must be true**:

✅ Jaeger service starts and responds to OTLP/HTTP  
✅ Prometheus scrapes OTel metrics  
✅ Grafana dashboard imports without errors  
✅ 6 dashboard panels display data  
✅ Trace flow end-to-end validated  
✅ Log correlation verified (trace_id in logs)  
✅ Backward compatibility maintained (OTEL_ENABLED=false works)  
✅ Performance impact < 5% (p50 latency)  
✅ No secrets leaked in tracing data  
✅ Exemplars storage bounded (< 100 per metric)  
✅ Sampling strategies working (Always, Never, Fixed, ParentBased, Error)  
✅ All OTel metrics available and flowing  

---

## Failure Scenarios & Recovery

### If Jaeger not responding:
- [ ] Check Jaeger logs: `docker logs jaeger-container`
- [ ] Verify OTLP/HTTP port 4318 open
- [ ] Verify network connectivity (if external)
- [ ] Restart Jaeger service
- [ ] Check storage backend (Elasticsearch, Cassandra, etc.)

### If Prometheus not scraping metrics:
- [ ] Check Prometheus targets: http://localhost:9090/targets
- [ ] Verify `/metrics` endpoint reachable
- [ ] Check Prometheus logs
- [ ] Verify scrape interval not too short
- [ ] Check firewall rules

### If Grafana dashboard fails to import:
- [ ] Verify data sources configured
- [ ] Check dashboard JSON syntax
- [ ] Verify JSON schema compliance
- [ ] Re-download dashboard from production branch
- [ ] Manually create dashboard if needed

### If performance impact exceeds threshold:
- [ ] Enable sampling (reduce from 1.0 to 0.1)
- [ ] Check ExemplarStorage bounded
- [ ] Verify no memory leaks in span processing
- [ ] Profile application to find bottleneck
- [ ] Consider disabling if impact unacceptable

### If secrets leaked in traces:
- [ ] Implement attribute filtering
- [ ] Add log redaction middleware
- [ ] Audit all span creation points
- [ ] Implement OpenTelemetry SamplingDecision to drop sensitive spans
- [ ] Consider disabling tracing until fixed

---

## Sign-Off

| Role | Name | Date | Status |
|------|------|------|--------|
| Tech Lead | TBD | — | ⏳ Pending |
| DevOps | TBD | — | ⏳ Pending |
| Chief Architect | Approved | 2026-07-13 | ✅ Approved |

---

## Next Steps

1. **Tech Lead**: Execute infrastructure validation checklist
2. **Tech Lead**: Document findings in INFRASTRUCTURE_VALIDATION_RESULTS.md
3. **DevOps**: Deploy to production upon validation pass
4. **DevOps**: Monitor OBS-002 metrics for first 24 hours
5. **Chief Architect**: Sign-off on production readiness

---

**Infrastructure Validation Gate Status**: ⏳ PENDING EXECUTION

Ready to proceed with validation checklist.
