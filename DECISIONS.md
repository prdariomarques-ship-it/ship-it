# Chief Architect Decisions Log
## Official Record of Governance Decisions

**Last Updated**: 2026-07-13  
**Format**: Chief Architect Decision Records (CADR)

---

## Decision 1: OBS-002 Phased Implementation Strategy

**ID**: CADR-001  
**Date**: 2026-07-02  
**Capability**: OBS-002 (Distributed Tracing)  
**Owner**: Implementation Engineer  
**Decision**: Approve 3-phase phased implementation approach

**Phases**:
1. Phase 1 (OBS-002A): OpenTelemetry setup + 3 auto-instrumentors
2. Phase 2 (OBS-002B): Trace propagation across 6 mechanisms
3. Phase 3 (OBS-002C): Trace correlation & operational metrics

**Rationale**:
- Smaller phases reduce risk and enable faster feedback
- Each phase can be independently tested and reviewed
- Allows for early detection of issues
- Enables parallel work on infrastructure setup while implementing propagation

**Constraints**:
- Phases must not break backward compatibility
- Each phase must pass full regression test suite
- Architecture frozen after Phase 1 design review

**Status**: APPROVED & IN_EXECUTION

---

## Decision 2: OpenTelemetry as Tracing Framework

**ID**: CADR-002  
**Date**: 2026-07-02  
**Capability**: OBS-002A  
**Owner**: Chief Architect  
**Decision**: Use OpenTelemetry (OTel) as official distributed tracing framework

**Rationale**:
- Industry standard (CNCF incubating project)
- Vendor-agnostic exporters (Jaeger, Honeycomb, Datadog, etc.)
- Automatic instrumentation for FastAPI, SQLAlchemy, httpx
- Well-maintained SDKs
- Community support and ecosystem

**Alternatives Considered**:
- Jaeger native SDK: Too vendor-specific
- DataDog APM: Vendor lock-in
- Custom implementation: Too much maintenance burden

**Constraints**:
- OTEL_ENABLED=false by default (no overhead when disabled)
- Console exporter when no backend configured (safe for dev/CI)
- Graceful degradation when backend unavailable

**Status**: APPROVED & IMPLEMENTED (Phase 1)

---

## Decision 3: W3C Trace Context Standard for Propagation

**ID**: CADR-003  
**Date**: 2026-07-05  
**Capability**: OBS-002B  
**Owner**: Chief Architect  
**Decision**: Use W3C Trace Context (RFC 9110) for all trace header propagation

**Format**: `traceparent: 00-{trace_id}-{span_id}-{trace_flags}`

**Rationale**:
- Official W3C standard (recommended by OWASP)
- Interoperable with all major observability platforms
- Widely adopted in industry
- Clear specification prevents ambiguity

**Implications**:
- All HTTP headers use `traceparent` field
- UUID4 request IDs converted to 32-char hex trace IDs
- Parent-child span relationships preserved across services
- Upstream trace ID takes precedence over local generation

**Status**: APPROVED & IMPLEMENTED (Phase 2)

---

## Decision 4: Phased Merge Strategy (Defer Until Complete)

**ID**: CADR-004  
**Date**: 2026-07-10  
**Capability**: OBS-002B  
**Owner**: Chief Architect  
**Decision**: Defer all OBS-002 merges to `main` until final capability completion

**Rationale**:
- Phased delivery keeps main branch clean
- Enables comprehensive testing across all phases
- Reduces risk of partial capability in production
- Allows for holistic validation

**Implications**:
- Each phase is validated independently
- Final merge happens only after all 3 phases approved
- Branch workflow.yaml tracks current state
- Merge authorization only after Final Capability Review gate

**Status**: APPROVED & IN_EXECUTION

---

## Decision 5: Sampling as Operational Concern (Phase 3)

**ID**: CADR-005  
**Date**: 2026-07-13  
**Capability**: OBS-002C  
**Owner**: Tech Lead  
**Decision**: Implement trace sampling as production operational concern (Phase 3)

**Strategies Provided**:
- Always (dev/testing)
- Never (no overhead)
- Fixed rate (e.g., 10% production sampling)
- Parent-based (inherit upstream decision)
- Error-based (always sample errors)

**Rationale**:
- Sampling reduces cost and load in production
- 5 strategies cover all common use cases
- Environment-configurable (OTEL_SAMPLING setting)
- Sampling rate exposed as metric for monitoring

**Trade-offs**:
- Not all requests captured (by design)
- Must sample errors at 100% to catch issues
- Configure parent-based for distributed traces

**Status**: APPROVED & IMPLEMENTED (Phase 3)

---

## Decision 6: Governance Evolution (AOM-v3.1)

**ID**: CADR-006  
**Date**: 2026-07-13  
**Capability**: AOM-v3.1 (Governance Only)  
**Owner**: Tech Lead  
**Decision**: Evolve Agent Operating Model to v3.1 with structured milestones and metrics

**New Governance Features**:
1. Capability Milestones (break capabilities into smaller units)
2. Separate Capability Status from Phase Status
3. workflow.yaml as single source of truth
4. PROJECT_STATUS.md (auto-updated)
5. ENGINEERING_SCOREBOARD.md (metrics tracking)
6. DECISIONS.md (this log)
7. CAPABILITY_RETROSPECTIVE.md (auto-generated)
8. Infrastructure Validation Gate
9. Phase Completion Rules
10. DELIVERY_PACKAGE.schema.json
11. Updated ROADMAP structure

**Rationale**:
- Reduce ambiguity in governance states
- Improve scalability for autonomous development
- Provide metrics and visibility
- Enable better decision-making
- Prepare for long-term platform evolution

**Constraints**:
- Zero changes to application architecture
- Full backward compatibility with AOM v3.0
- No changes to completed capabilities (OBS-002A/B/C)
- Governance-only evolution

**Status**: APPROVED & IMPLEMENTATION_IN_PROGRESS

---

## Decision 7: Infrastructure Validation Gate for OBS-002

**ID**: CADR-007  
**Date**: 2026-07-13  
**Capability**: OBS-002C  
**Owner**: Tech Lead  
**Decision**: Introduce Infrastructure Validation gate for trace correlation features

**Applies To**:
- Docker (Jaeger service)
- Networking (OTLP/HTTP endpoint)
- Prometheus (exemplar metrics)
- Grafana (dashboard)
- External backends (Jaeger, Prometheus)

**Validation Criteria**:
- Jaeger service starts and responds
- OTLP/HTTP endpoint reachable
- Prometheus scrapes metrics
- Grafana dashboard imports without errors
- Logs include trace_id correlation

**Status**: DEFERRED (after OBS-002C merge approval)

---

## Decision 8: Log-to-Trace Correlation in Phase 3

**ID**: CADR-008  
**Date**: 2026-07-13  
**Capability**: OBS-002C  
**Owner**: Implementation Engineer  
**Decision**: Add trace_id to all log records (text and JSON formats)

**Implementation**:
- RequestIDFilter extended to include trace_id
- Format: `[request_id:trace_id]` in text logs
- JSON logs include "trace_id" field
- Enables grepping logs by trace ID

**Rationale**:
- Log-to-trace navigation (find logs for a trace)
- Reduced MTTR for debugging in production
- Zero performance impact (ContextVar lookup)
- Backward compatible (trace_id="-" when not in request)

**Status**: APPROVED & IMPLEMENTED (Phase 3)

---

## Decision 9: Exemplar-Based Metric-to-Trace Linking

**ID**: CADR-009  
**Date**: 2026-07-13  
**Capability**: OBS-002C  
**Owner**: Implementation Engineer  
**Decision**: Use Prometheus exemplars for metric-to-trace correlation

**Implementation**:
- ExemplarStorage holds (trace_id, span_id, value) tuples
- Max 100 exemplars per metric (bounded memory)
- Grafana dashboard shows exemplar links
- Clickable trace_id links to Jaeger trace

**Rationale**:
- Metric-to-trace navigation (drill down from metric to trace)
- Reduced MTTR for performance investigations
- Bounded memory (FIFO eviction at max)
- Works with existing Prometheus + Grafana stack

**Status**: APPROVED & IMPLEMENTED (Phase 3)

---

## Decision 10: Backward Compatibility First

**ID**: CADR-010  
**Date**: 2026-07-13  
**Capability**: OBS-002 (All Phases)  
**Owner**: Chief Architect  
**Decision**: All OBS-002 features must maintain 100% backward compatibility

**Requirements**:
- OTEL_ENABLED=false disables all tracing (default)
- No breaking changes to existing APIs
- Trace correlation is opt-in via logging config
- Sampling defaults to safe parent-based strategy
- Graceful degradation when backends unavailable

**Rationale**:
- Zero risk of breaking existing functionality
- Safe to deploy in production without extensive retesting
- Enables gradual rollout and validation
- Reduces operational risk

**Status**: APPROVED & ENFORCED (all phases)

---

## Summary

| Decision | Status | Phase | Impact |
|----------|--------|-------|--------|
| CADR-001 | ✅ APPROVED | OBS-002 | 3-phase strategy approved |
| CADR-002 | ✅ APPROVED | OBS-002A | OpenTelemetry selected |
| CADR-003 | ✅ APPROVED | OBS-002B | W3C Trace Context standard |
| CADR-004 | ✅ APPROVED | OBS-002 | Defer merge until complete |
| CADR-005 | ✅ APPROVED | OBS-002C | Sampling strategies |
| CADR-006 | ✅ APPROVED | AOM-v3.1 | Governance evolution |
| CADR-007 | ⏳ PENDING | OBS-002C | Infrastructure validation |
| CADR-008 | ✅ APPROVED | OBS-002C | Log-trace correlation |
| CADR-009 | ✅ APPROVED | OBS-002C | Exemplar metric linking |
| CADR-010 | ✅ APPROVED | OBS-002 | Backward compatibility |

---

**Next Gate**: Final Capability Review (Chief Architect) → Merge Authorization → Production Deployment
