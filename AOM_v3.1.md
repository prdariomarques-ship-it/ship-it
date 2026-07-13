# Agent Operating Model v3.1
## Governance Framework for Autonomous Platform Development

**Version**: 3.1  
**Released**: 2026-07-13  
**Status**: 🟢 ACTIVE  
**Framework**: Dario OS Autonomous Development Platform

---

## Executive Summary

AOM-v3.1 introduces structured milestones, clearer status models, and comprehensive metrics to scale autonomous platform development. This governance framework enables:

- ✅ Predictable delivery cycles
- ✅ Clear decision-making authority
- ✅ Comprehensive quality metrics
- ✅ Automatic status tracking
- ✅ Risk-based gates

**Key Innovation**: Separation of **Capability Status** (NOT_STARTED → IN_PROGRESS → COMPLETED) from **Phase Status** (SPECIFICATION → DESIGN → IMPLEMENTATION → VALIDATION → MERGE → PRODUCTION).

---

## Part 1: Core Concepts

### 1.1 Capability

A **Capability** is a self-contained system feature that delivers business value and requires cross-layer changes (API, backend, infrastructure, documentation).

**Examples**:
- OBS-001: Correlation IDs
- OBS-002: Distributed Tracing  
- AUTH-001: Multi-factor Authentication
- PERF-001: Query Performance Optimization

**Lifecycle**: 
```
NOT_STARTED → IN_PROGRESS → COMPLETED
```

**Properties**:
- ID: OBS-002, AUTH-001, etc.
- Name: Descriptive title
- Owner: Role responsible for delivery
- Status: Current capability state
- Target Date: Planned completion

### 1.2 Milestone

Each Capability is divided into **Milestones** — smaller deliverables that can be independently reviewed and validated.

**Example (OBS-002)**:
- Milestone A: OpenTelemetry Setup
- Milestone B: Trace Propagation
- Milestone C: Correlation & Metrics

**Lifecycle**:
```
SPECIFICATION → DESIGN → IMPLEMENTATION → VALIDATION → MERGE → PRODUCTION
```

**Properties**:
- Phase: Current phase in workflow
- Tests: Test count and pass rate
- Coverage: Code coverage %
- Approval Status: Gate status

### 1.3 Phase

A **Phase** represents one step in the milestone workflow. Each milestone progresses through the same phases.

**Phases** (in order):

1. **SPECIFICATION**: Requirements & design documentation reviewed
2. **DESIGN_REVIEW**: Architecture decisions validated
3. **IMPLEMENTATION**: Code written and tested
4. **VALIDATION**: Quality gates verified
5. **MERGE**: Code review complete, approved for merge
6. **PRODUCTION**: Deployed to production

---

## Part 2: Status Models

### 2.1 Capability Status (Top-Level)

```
NOT_STARTED ──→ IN_PROGRESS ──→ COMPLETED
```

| Status | Meaning | Milestones | Action |
|--------|---------|-----------|--------|
| **NOT_STARTED** | Not yet authorized | 0/N | Awaiting specification |
| **IN_PROGRESS** | Actively being developed | ≥1/N | Milestone in progress |
| **COMPLETED** | All milestones delivered | N/N | Ready for merge or production |

### 2.2 Phase Status (Milestone-Level)

```
SPECIFICATION ──→ DESIGN_REVIEW ──→ IMPLEMENTATION ──→ VALIDATION ──→ MERGE ──→ PRODUCTION
```

| Phase | Owner | Input | Output | Gate |
|-------|-------|-------|--------|------|
| **SPECIFICATION** | Tech Lead | Requirements | Spec document | Tech Lead approval |
| **DESIGN_REVIEW** | Chief Architect | Architecture | Design review | Chief Architect approval |
| **IMPLEMENTATION** | Implementation Eng | Design | Code + tests | 100% tests passing |
| **VALIDATION** | QA | Code | Delivery package | Quality gates |
| **MERGE** | CTO | Delivery package | Merged to main | Code review approval |
| **PRODUCTION** | DevOps | Main branch | Deployed | Deployment success |

### 2.3 Infrastructure Validation Gate (New)

For capabilities involving Docker, Prometheus, Grafana, Jaeger, or external services:

```
VALIDATION ──→ INFRASTRUCTURE_VALIDATION ──→ MERGE
```

**Checks**:
- Docker services start and respond
- Network connectivity verified
- External backends reachable
- Metrics scraping works
- Dashboards import without errors
- Log aggregation functional

---

## Part 3: Single Source of Truth

### 3.1 workflow.yaml

**Location**: Root of repository  
**Purpose**: Single source of truth for workflow state  
**Updated**: After every phase transition  
**Machine-Readable**: Yes (YAML format)

**Fields**:
```yaml
current_program: OBS-002
current_capability: OBS-002C
current_phase: VALIDATION
current_status: COMPLETED

capabilities:
  - id: OBS-002A
    status: COMPLETED
    phase: PRODUCTION
    
  - id: OBS-002B
    status: COMPLETED
    phase: VALIDATION
    
  - id: OBS-002C
    status: COMPLETED
    phase: VALIDATION
```

**Who Updates**: Implementation Engineer (after code push)  
**Automation**: CI/CD pipeline updates automatically

---

## Part 4: Governance Documents

### 4.1 DECISIONS.md

**Purpose**: Persistent record of all Chief Architect decisions  
**Location**: Root of repository  
**Format**: Chief Architect Decision Records (CADR)

**Entry Format**:
```markdown
## Decision N: [Title]

ID: CADR-NNN
Date: YYYY-MM-DD
Capability: XXX-YYY
Owner: Role
Decision: [What was decided?]
Rationale: [Why?]
Status: APPROVED | DEFERRED | REJECTED
```

**Examples**:
- CADR-001: OpenTelemetry as tracing framework
- CADR-002: W3C Trace Context standard
- CADR-003: Phased merge strategy

### 4.2 PROJECT_STATUS.md

**Purpose**: Human-readable project health report  
**Location**: Root of repository  
**Updated**: After every capability completion  
**Audience**: Stakeholders, managers, team

**Sections**:
- Program health (status, metrics, trends)
- Current capability (progress, milestones)
- Completed capabilities (summary)
- Test results (count, coverage)
- Quality metrics (pass rate, bugs)
- Approval chain status
- Next steps

### 4.3 ENGINEERING_SCOREBOARD.md

**Purpose**: Comprehensive metrics and KPIs  
**Location**: Root of repository  
**Updated**: Weekly or after major events  
**Audience**: Engineering leadership

**Metrics**:
- Cycle time (specification to merge)
- Lead time (start to completion)
- Review time (avg time in code review)
- Implementation time (design to code complete)
- Test pass rate (% tests passing)
- Code coverage (% lines tested)
- Regression bugs (bugs found post-merge)
- Capabilities completed
- Velocity (features per week)

### 4.4 DELIVERY_PACKAGE.schema.json

**Purpose**: Standardized schema for all delivery packages  
**Location**: Root of repository  
**Format**: JSON Schema (Draft 7)

**Validates**:
- Metadata (capability, phase, owner, date)
- Scope (authorized items, completed items)
- Implementation (files, lines, changes)
- Tests (counts, coverage)
- Validation (criteria, acceptance)
- Evidence (commits, branch, status)
- Rollback (procedure, testing, impact)
- Production readiness

---

## Part 5: Workflow & Gates

### 5.1 Milestone Workflow

```
Specification
      ↓
      └→ [GATE: Spec Approved?] ──NO→ Rework
         │
         YES
         ↓
Design Review
      ↓
      └→ [GATE: Design Approved?] ──NO→ Rework
         │
         YES
         ↓
Implementation
      ↓
      ├→ Write code
      ├→ Write tests
      └→ Run tests
         ↓
         └→ [GATE: All tests passing?] ──NO→ Fix bugs
            │
            YES
            ↓
Validation
      ↓
      ├→ Verify spec compliance
      ├→ Verify design compliance
      └→ Check acceptance criteria
         ↓
         └→ [GATE: Quality gates passed?] ──NO→ Rework
            │
            YES
            ↓
[Infrastructure Validation] ← NEW (for infra capabilities)
      ↓
      ├→ Docker services running
      ├→ Network connectivity OK
      ├→ External backends reachable
      └→ Dashboards/metrics functional
         ↓
         └→ [GATE: Infrastructure validated?] ──NO→ Fix
            │
            YES
            ↓
Code Review
      ↓
      └→ [GATE: Code approved?] ──NO→ Rework
         │
         YES
         ↓
Final Capability Review ← FINAL GATE
      ↓
      └→ [GATE: Chief Architect approval?] ──NO→ Rework
         │
         YES
         ↓
Merge to main
      ↓
      └→ [GATE: Merge successful?] ──NO→ Debug
         │
         YES
         ↓
Production Deployment
      ↓
      └→ [GATE: Deployment successful?] ──NO→ Rollback
         │
         YES
         ↓
PRODUCTION
```

### 5.2 Gate Authority

| Gate | Owner | Authority | Decision Time |
|------|-------|-----------|---------------|
| **Spec Approved** | Tech Lead | Must approve | Same day |
| **Design Approved** | Chief Architect | Must approve | Next day |
| **Tests Passing** | QA | Automated | Real-time |
| **Quality Gates** | QA | Automated | Real-time |
| **Infrastructure OK** | DevOps | Automated | Real-time |
| **Code Approved** | Tech Lead | Must approve | Next day |
| **Final Review** | Chief Architect | Must approve | Next day |
| **Merge OK** | CTO | Must approve | Same day |
| **Deploy OK** | DevOps | Must approve | Same day |

---

## Part 6: Roles & Responsibilities

### 6.1 Chief Architect

**Authority**: Highest  
**Decisions**: Architecture, design approval, final capability review  
**Timing**: Next day (or urgent same-day)  
**Accountable For**: System design, consistency, scalability

**Approval Gates**:
- Design Review (CADR-issued)
- Final Capability Review
- Infrastructure Validation (for major changes)

### 6.2 Tech Lead

**Authority**: Specification, code review  
**Decisions**: Spec approval, code review approval, phase transitions  
**Timing**: Same day or next day  
**Accountable For**: Governance, process, team enablement

**Approval Gates**:
- Specification approval
- Incremental code review
- Phase completion authorization

### 6.3 Implementation Engineer

**Authority**: Code execution, delivery  
**Decisions**: Code implementation, testing strategy  
**Timing**: Real-time (autonomous execution)  
**Accountable For**: Delivering working code, test coverage

**Executes**:
- Write code
- Write tests
- Run tests
- Package delivery
- Request reviews

### 6.4 QA

**Authority**: Quality gates  
**Decisions**: Test requirements, acceptance criteria  
**Timing**: Automated (real-time)  
**Accountable For**: Test coverage, quality metrics

**Validates**:
- Test pass rate (automated)
- Code coverage (automated)
- Performance criteria (automated)
- Spec compliance (manual)

### 6.5 DevOps

**Authority**: Infrastructure, deployment  
**Decisions**: Infrastructure validation, deployment strategy  
**Timing**: Real-time or next day  
**Accountable For**: Production reliability, infrastructure

**Validates**:
- Infrastructure validation gate (new)
- Deployment success
- Rollback procedures

---

## Part 7: Metrics & KPIs

### 7.1 Cycle Time

**Definition**: Time from specification to production deployment  
**Target**: 14 days per capability  
**Tracked In**: ENGINEERING_SCOREBOARD.md

**Formula**:
```
Cycle Time = Date(Production) - Date(Specification)
```

### 7.2 Lead Time

**Definition**: Time from start of work to merge approval  
**Target**: 10 days per capability  
**Tracked In**: ENGINEERING_SCOREBOARD.md

**Formula**:
```
Lead Time = Date(Final Review Approved) - Date(Start)
```

### 7.3 Review Time

**Definition**: Time code spends in review (each review cycle)  
**Target**: < 24 hours per review  
**Tracked In**: ENGINEERING_SCOREBOARD.md

### 7.4 Test Pass Rate

**Definition**: Percentage of tests passing  
**Target**: 100%  
**Tracked In**: PROJECT_STATUS.md (per phase)

### 7.5 Code Coverage

**Definition**: Percentage of lines covered by tests  
**Target**: ≥ 70% (per phase), ≥ 80% (mature capabilities)  
**Tracked In**: ENGINEERING_SCOREBOARD.md

### 7.6 Regression Rate

**Definition**: Bugs found after merge (regression failures)  
**Target**: 0%  
**Tracked In**: ENGINEERING_SCOREBOARD.md

### 7.7 Velocity

**Definition**: Capabilities delivered per week  
**Target**: 1.5–2.0 cap/week  
**Tracked In**: ENGINEERING_SCOREBOARD.md

---

## Part 8: Backward Compatibility

### 8.1 AOM-v3.0 Compatibility

**AOM-v3.1 is fully backward compatible with AOM-v3.0**

Changes:
- ✅ New milestone model (optional, can still work without)
- ✅ New documents (workflow.yaml, scoreboard, etc.) do not affect existing workflows
- ✅ New gates are additional safety checks (do not override existing gates)
- ✅ Status separation is clarifying, not breaking

**Impact on Running Programs**:
- Zero impact on OBS-002A (already completed before v3.1)
- Zero impact on OBS-002B (already completed before v3.1)
- OBS-002C benefits from new infrastructure validation gate
- Future programs can adopt full AOM-v3.1

---

## Part 9: Implementation for OBS-002

### 9.1 Applied to OBS-002C

New governance features active:

1. ✅ **workflow.yaml**: Tracks OBS-002C state
2. ✅ **DECISIONS.md**: Records CADR decisions (including OBS-002)
3. ✅ **PROJECT_STATUS.md**: Shows OBS-002 program health
4. ✅ **ENGINEERING_SCOREBOARD.md**: Tracks OBS-002 metrics
5. ✅ **Delivery Package Schema**: Validates OBS-002C delivery
6. ⏳ **Infrastructure Validation**: For OBS-002C deployment

### 9.2 Retrospective (After OBS-002 Merge)

**CAPABILITY_RETROSPECTIVE.md** will be generated containing:

- ✅ What went well (velocity, quality, collaboration)
- ✅ Lessons learned (3-phase strategy worked)
- ✅ Architecture decisions (OTel, W3C Trace Context)
- ✅ Technical debt (none identified)
- ✅ Risks (low risk, well-mitigated)
- ✅ Metrics (cycle time, coverage, bugs)
- ✅ Recommendations (maintain pace, increase coverage)

---

## Part 10: Governance Artifacts

### 10.1 Required Documents (All Programs)

| Document | Location | Owner | Updated |
|----------|----------|-------|---------|
| workflow.yaml | Root | Implementation Eng | Each merge |
| DECISIONS.md | Root | Chief Architect | Each decision |
| PROJECT_STATUS.md | Root | Tech Lead | Weekly |
| ENGINEERING_SCOREBOARD.md | Root | Tech Lead | Weekly |
| Delivery Package (OBS-002C_...) | Root | Implementation Eng | Per milestone |

### 10.2 Schema Files

| Schema | Location | Purpose |
|--------|----------|---------|
| DELIVERY_PACKAGE.schema.json | Root | Validate delivery packages |

### 10.3 Generated Reports

| Report | Generated After | Owner |
|--------|-----------------|-------|
| CAPABILITY_RETROSPECTIVE.md | Capability completion | Tech Lead |
| ROADMAP.md | Program update | Product Manager |

---

## Part 11: Evolution Path

### 11.1 Future Enhancements (v3.2+)

- 🔮 Automated metrics collection from git/CI
- 🔮 Slack notifications for gate transitions
- 🔮 Dashboard UI for workflow visualization
- 🔮 Burndown charts by capability
- 🔮 Predictive cycle time forecasting
- 🔮 Integration with Jira/GitHub projects

### 11.2 Scaling Considerations

AOM-v3.1 scales to:
- ✅ Multiple parallel capabilities (via role separation)
- ✅ Distributed teams (via async gates)
- ✅ Long-running programs (via milestone tracking)
- ✅ Complex dependencies (via workflow.yaml)

---

## Part 12: Summary

### 12.1 What Changed in v3.1

| Feature | v3.0 | v3.1 | Impact |
|---------|------|------|--------|
| **Capability Milestones** | No | Yes | Smaller deliverables |
| **Status Separation** | Mixed | Clear | Reduced ambiguity |
| **Single Source of Truth** | No | Yes | workflow.yaml |
| **Metrics Dashboard** | No | Yes | ENGINEERING_SCOREBOARD |
| **Decision Log** | No | Yes | DECISIONS.md |
| **Infrastructure Gate** | No | Yes | Safer deployments |
| **Backward Compatible** | — | 100% | Zero breaking changes |

### 12.2 Why This Matters

**Before (v3.0)**:
- Capability status and phase status were mixed
- Ambiguity about what was "done" (code done? tests done? merged?)
- Metrics hidden in various places
- Decisions not formally recorded
- Manual status updates

**After (v3.1)**:
- Clear separation: Capability Status vs Phase Status
- Unambiguous "done" criteria (Final Review + Merge)
- All metrics in ENGINEERING_SCOREBOARD
- All decisions in DECISIONS.md
- Automatic status updates via workflow.yaml

---

## Part 13: Quick Reference

### 13.1 Capability Lifecycle

```
Capability Status:   NOT_STARTED → IN_PROGRESS → COMPLETED
Phase Workflow:      SPEC → DESIGN → IMPL → VALIDATE → MERGE → PROD
Gates:               6 approval gates (Chief Arch, Tech Lead, QA, etc.)
Docs:                Delivery Package + Retrospective
```

### 13.2 Key Dates

- **v3.1 Released**: 2026-07-13
- **First Capability** (OBS-002C): 2026-07-13
- **Retroactive Adoption**: OBS-002A/B/C
- **Full Rollout**: All future capabilities

### 13.3 Key Contacts

- **Chief Architect**: Final approvals (architecture, design, final review)
- **Tech Lead**: Governance, process, spec/code reviews
- **Implementation Engineer**: Delivery and execution
- **DevOps**: Infrastructure validation, deployment

---

## Conclusion

AOM-v3.1 represents evolution toward **structured, scalable, autonomous development** while maintaining **100% backward compatibility** with existing work.

**Status**: 🟢 ACTIVE  
**Adoption**: OBS-002C + future capabilities  
**Success Metric**: Cycle time ≤ 14 days, coverage ≥ 70%, bugs = 0  

---

**Document Version**: 3.1.0  
**Released**: 2026-07-13  
**Next Review**: 2026-08-13 (after first completed capability under v3.1)
