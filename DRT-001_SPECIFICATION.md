# DRT-001 SPECIFICATION: Workflow Engine + State Machine (MVP)

**Capability ID:** DRT-001  
**Title:** Workflow Engine + State Machine (Minimum Viable Product)  
**Version:** 1.0 MVP  
**Authority:** Chief Architect  
**Date:** 2026-07-13  
**Status:** READY_FOR_IMPLEMENTATION  

---

## EXECUTIVE SUMMARY

DRT-001 is the **minimal production-usable Runtime** that can execute one complete capability lifecycle automatically without manual state manipulation.

**Not a framework.** A working capability execution engine.

### MVP Philosophy

- ✅ Every component has immediate operational value
- ✅ Every component executes real capabilities today
- ✅ Deployable incrementally (daily if needed)
- ✅ No framework code with future-only value
- ✅ Measurable by actual capability execution, not test coverage

### What DRT-001 Does

```
1. Load current capability state from workflow.yaml
2. Validate next transition (DAG rules)
3. Execute transition atomically
4. Persist new state to workflow.yaml
5. Record in immutable audit log
6. Expose API for querying state and history
7. Report health (ready to execute or degraded)

Result: One complete capability lifecycle
        SPECIFICATION → DESIGN → IMPLEMENTATION → QA → FINAL → MERGE → CLOSED
        All transitions automatic, no manual intervention
```

---

## COMPONENTS (MVP ONLY)

### Component 1: Workflow Engine

**Responsibility:** Read/write capability state, manage workflow.yaml

```python
class WorkflowEngine:
    """Persistent capability state management."""
    
    def __init__(self, workflow_file: Path):
        self.workflow_file = workflow_file
        self.state_cache = {}
    
    def load_state(self, capability_id: str) -> Dict:
        """Load current state from workflow.yaml."""
        # Parse YAML, extract capability record
        # Return: {phase, status, owner, gates_completed}
    
    def update_phase(self, capability_id: str, new_phase: str) -> bool:
        """Atomically update phase in workflow.yaml."""
        # Acquire file lock
        # Read current state
        # Update phase field
        # Write back to YAML
        # Release lock
        # Return: success
    
    def update_owner(self, capability_id: str, new_owner: str) -> bool:
        """Atomically update owner."""
        # Same pattern as update_phase
    
    def record_gate(self, capability_id: str, gate: str, status: str) -> bool:
        """Record gate completion."""
        # Add to gates_completed list
        # Update timestamp
```

**Deliverables:**
- `backend/governance/workflow_engine.py` (200 lines)
- No external dependencies (file-based only)
- YAML atomic writes (file locking)

**Tests:**
- Load state from workflow.yaml ✓
- Update phase atomically ✓
- Update owner atomically ✓
- Record gate completion ✓
- Persist correctly ✓
- Handle missing capability ✓

---

### Component 2: State Machine

**Responsibility:** Validate transitions, enforce DAG rules

```python
class StateMachine:
    """Enforce valid state transitions (DAG)."""
    
    VALID_TRANSITIONS = {
        "SPECIFICATION": ["DESIGN_REVIEW"],
        "DESIGN_REVIEW": ["IMPLEMENTATION"],
        "IMPLEMENTATION": ["CODE_REVIEW", "QA"],
        "CODE_REVIEW": ["FINAL_REVIEW"],
        "QA": ["FINAL_REVIEW"],
        "FINAL_REVIEW": ["MERGE_AUTHORIZATION"],
        "MERGE_AUTHORIZATION": ["CLOSED"],
        "CLOSED": [],  # Terminal state
    }
    
    def is_valid_transition(self, current: str, next_phase: str) -> bool:
        """Check if transition is allowed."""
        if current not in self.VALID_TRANSITIONS:
            return False
        return next_phase in self.VALID_TRANSITIONS[current]
    
    def get_valid_next(self, current: str) -> List[str]:
        """Get all valid next phases."""
        return self.VALID_TRANSITIONS.get(current, [])
    
    def is_terminal(self, phase: str) -> bool:
        """Check if phase is terminal."""
        return phase == "CLOSED"
```

**Deliverables:**
- `backend/governance/state_machine.py` (100 lines)
- No external dependencies
- Pure validation logic

**Tests:**
- Valid transitions accepted ✓
- Invalid transitions rejected ✓
- Terminal states detected ✓
- All 8 phases have valid paths ✓

---

### Component 3: Event Bus (Internal Only)

**Responsibility:** Publish events for audit trail, internal-only

```python
class EventBus:
    """Internal pub-sub for audit trail."""
    
    def __init__(self):
        self.subscribers = {}  # event_type → [handlers]
        self.event_history = []  # All events ever
    
    def emit(self, event_type: str, data: Dict) -> None:
        """Publish internal event."""
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": data
        }
        
        # Record in history
        self.event_history.append(event)
        
        # Notify subscribers
        for handler in self.subscribers.get(event_type, []):
            try:
                handler(event)
            except Exception:
                pass  # Fail-safe
    
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Register event listener."""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(handler)
    
    def get_history(self) -> List[Dict]:
        """Get all events (for audit)."""
        return list(self.event_history)
```

**Deliverables:**
- `backend/runtime/event_bus.py` (80 lines)
- In-memory only (no Redis required for MVP)
- 5 core events: PHASE_TRANSITIONED, OWNER_CHANGED, GATE_RECORDED, ERROR, HEALTH_CHECK

**Tests:**
- Emit event ✓
- Subscribe to event ✓
- Event history maintained ✓
- Multiple subscribers called ✓

---

### Component 4: Audit Engine

**Responsibility:** Persist every state change (immutable log)

```python
class AuditEngine:
    """Immutable audit trail."""
    
    def __init__(self, audit_file: Path):
        self.audit_file = audit_file
        self.entries = []  # Load on init
    
    def record(self, capability_id: str, event_type: str, 
               details: Dict) -> None:
        """Record immutable audit entry."""
        entry = {
            "entry_id": f"AE-{len(self.entries)}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "capability": capability_id,
            "event": event_type,
            "details": details
        }
        
        # Append to audit file (never modify)
        self.entries.append(entry)
        self._persist(entry)
    
    def get_history(self, capability_id: str) -> List[Dict]:
        """Get audit trail for capability."""
        return [e for e in self.entries 
                if e["capability"] == capability_id]
    
    def _persist(self, entry: Dict) -> None:
        """Append entry to audit file."""
        with open(self.audit_file, 'a') as f:
            f.write(json.dumps(entry) + "\n")
```

**Deliverables:**
- `backend/audit/audit_engine.py` (100 lines)
- Append-only JSON log file
- No modifications, only appends
- One line per entry (easy to replay)

**Tests:**
- Record audit entry ✓
- Audit file grows ✓
- Immutability verified (no modifications) ✓
- History retrieval works ✓

---

### Component 5: Runtime API

**Responsibility:** HTTP endpoints for state query and transition

```python
from fastapi import FastAPI, HTTPException

app = FastAPI()

@app.get("/runtime/state/{capability_id}")
async def get_state(capability_id: str):
    """Get current state of capability."""
    state = workflow_engine.load_state(capability_id)
    return {
        "capability_id": capability_id,
        "phase": state["phase"],
        "owner": state["owner"],
        "gates_completed": state.get("gates_completed", []),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

@app.get("/runtime/history/{capability_id}")
async def get_history(capability_id: str):
    """Get audit trail for capability."""
    history = audit_engine.get_history(capability_id)
    return {
        "capability_id": capability_id,
        "entries": history
    }

@app.post("/runtime/transition/{capability_id}")
async def transition(capability_id: str, request: TransitionRequest):
    """Execute state transition."""
    current_state = workflow_engine.load_state(capability_id)
    current_phase = current_state["phase"]
    
    # Validate transition
    if not state_machine.is_valid_transition(current_phase, request.next_phase):
        raise HTTPException(status_code=400, 
                          detail=f"Invalid transition: {current_phase} → {request.next_phase}")
    
    # Execute transition
    workflow_engine.update_phase(capability_id, request.next_phase)
    event_bus.emit("PHASE_TRANSITIONED", {
        "capability": capability_id,
        "from_phase": current_phase,
        "to_phase": request.next_phase
    })
    audit_engine.record(capability_id, "PHASE_TRANSITIONED", {
        "from": current_phase,
        "to": request.next_phase,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })
    
    return {
        "capability_id": capability_id,
        "phase": request.next_phase,
        "success": True
    }

@app.get("/runtime/health")
async def health():
    """Runtime health status."""
    return {
        "status": "HEALTHY",
        "components": {
            "workflow_engine": "READY",
            "state_machine": "READY",
            "audit_engine": "READY",
            "event_bus": "READY"
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

class TransitionRequest(BaseModel):
    next_phase: str
```

**Deliverables:**
- `backend/runtime/runtime_api.py` (150 lines)
- 4 endpoints: GET state, GET history, POST transition, GET health
- FastAPI (lightweight, built-in validation)

**Tests:**
- GET /runtime/state/{id} ✓
- GET /runtime/history/{id} ✓
- POST /runtime/transition/{id} valid ✓
- POST /runtime/transition/{id} invalid ✓
- GET /runtime/health ✓

---

### Component 6: Health Manager

**Responsibility:** Check if Runtime is ready to execute capabilities

```python
class HealthManager:
    """Unified health status."""
    
    def __init__(self, workflow_engine, audit_engine, event_bus):
        self.workflow_engine = workflow_engine
        self.audit_engine = audit_engine
        self.event_bus = event_bus
    
    def check_health(self) -> Dict:
        """Check runtime health."""
        health = {
            "status": "HEALTHY",
            "components": {},
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        # Check workflow engine
        try:
            # Try to load any state (verify YAML accessible)
            self.workflow_engine.load_state("TEST")
        except:
            health["components"]["workflow_engine"] = "DEGRADED"
            health["status"] = "DEGRADED"
        else:
            health["components"]["workflow_engine"] = "HEALTHY"
        
        # Check audit engine
        try:
            # Verify audit file accessible
            self.audit_engine.get_history("TEST")
        except:
            health["components"]["audit_engine"] = "DEGRADED"
            health["status"] = "DEGRADED"
        else:
            health["components"]["audit_engine"] = "HEALTHY"
        
        # Event bus always healthy (in-memory)
        health["components"]["event_bus"] = "HEALTHY"
        
        return health
    
    def is_ready(self) -> bool:
        """Can Runtime execute capabilities?"""
        health = self.check_health()
        return health["status"] == "HEALTHY"
```

**Deliverables:**
- `backend/operations/health_manager.py` (100 lines)
- No external dependencies
- Quick checks (<100ms)

**Tests:**
- Healthy state detected ✓
- Degraded state detected ✓
- is_ready() returns correct value ✓

---

## EXCLUDED FROM MVP (Future Capabilities)

These belong to DRT-002 through DRT-006:

❌ **Policy Engine** (DRT-006) — Not needed for first lifecycle  
❌ **Metrics Engine** (DRT-006) — Not needed for first lifecycle  
❌ **Artifact Registry** (DRT-004) — Not needed for first lifecycle  
❌ **Notification Engine** (DRT-005) — Not needed for first lifecycle  
❌ **Recovery Manager** (DRT-005) — Not needed for first lifecycle  
❌ **Distributed Locks** (DRT-006) — Single capability per Runtime OK  
❌ **Retry Engine** — Transitions don't fail in MVP  
❌ **Parallel Scheduler** — Sequential execution OK for MVP  

---

## SUCCESS SCENARIO: Complete Lifecycle Execution

**Initial State (workflow.yaml):**
```yaml
current_program:
  id: TEST-CAP-001
  name: "Test Capability"
  phase: SPECIFICATION
  owner: chief-architect
  status: IN_PROGRESS
```

**Automatic Execution (No Manual Intervention):**

```
1. API: GET /runtime/state/TEST-CAP-001
   ← {phase: "SPECIFICATION", owner: "chief-architect"}
   ✓ Audit logged

2. API: POST /runtime/transition/TEST-CAP-001
   {next_phase: "DESIGN_REVIEW"}
   ✓ State updated
   ✓ Event emitted
   ✓ Audit logged
   
3. API: GET /runtime/state/TEST-CAP-001
   ← {phase: "DESIGN_REVIEW", owner: "chief-architect"}

4. API: POST /runtime/transition/TEST-CAP-001
   {next_phase: "IMPLEMENTATION"}
   ✓ State updated
   ✓ Event emitted
   ✓ Audit logged

... continue through all phases ...

8. API: POST /runtime/transition/TEST-CAP-001
   {next_phase: "CLOSED"}
   ✓ State updated
   ✓ Terminal state reached
   ✓ Event emitted
   ✓ Audit logged

9. API: GET /runtime/history/TEST-CAP-001
   ← [
       {entry: PHASE_TRANSITIONED, from: SPECIFICATION, to: DESIGN_REVIEW},
       {entry: PHASE_TRANSITIONED, from: DESIGN_REVIEW, to: IMPLEMENTATION},
       ...
       {entry: PHASE_TRANSITIONED, from: MERGE_AUTHORIZATION, to: CLOSED}
     ]
   ✓ Complete audit trail
```

**Result:** One complete capability lifecycle executed by Runtime, zero manual state manipulation.

---

## DELIVERABLES (MVP)

### Code (650 lines total)

- `backend/governance/workflow_engine.py` (200 lines)
- `backend/governance/state_machine.py` (100 lines)
- `backend/runtime/event_bus.py` (80 lines)
- `backend/audit/audit_engine.py` (100 lines)
- `backend/runtime/runtime_api.py` (150 lines)
- `backend/operations/health_manager.py` (100 lines)

### Tests (400+ lines)

- `tests/governance/test_workflow_engine.py` (80 lines)
- `tests/governance/test_state_machine.py` (50 lines)
- `tests/runtime/test_event_bus.py` (50 lines)
- `tests/audit/test_audit_engine.py` (70 lines)
- `tests/runtime/test_runtime_api.py` (100 lines)
- `tests/operations/test_health_manager.py` (50 lines)

### Infrastructure

- `helm/drt-001-workflow-engine/Chart.yaml` (50 lines)
- `helm/drt-001-workflow-engine/values.yaml` (30 lines)
- `helm/drt-001-workflow-engine/templates/deployment.yaml` (80 lines)

### Documentation

- `docs/DRT-001_API.md` (Endpoint reference)
- `docs/DRT-001_DEPLOYMENT.md` (Helm deployment guide)
- `docs/DRT-001_OPERATIONS.md` (Runbook for ops team)

---

## TEST COVERAGE

**Target:** ≥90% across all components

### Component-Level Tests

| Component | Test Count | Coverage Target |
|-----------|-----------|-----------------|
| WorkflowEngine | 12 tests | 95% |
| StateMachine | 8 tests | 98% |
| EventBus | 6 tests | 92% |
| AuditEngine | 8 tests | 96% |
| RuntimeAPI | 15 tests | 90% |
| HealthManager | 6 tests | 94% |
| **TOTAL** | **55+ tests** | **≥90%** |

### Test Categories

**Valid Paths (40% of tests):**
- Load state ✓
- Valid transitions ✓
- Update phase ✓
- Record gates ✓
- API endpoints ✓

**Error Paths (30% of tests):**
- Invalid transitions rejected ✓
- Missing capability handled ✓
- Corrupted YAML handled ✓
- API validation errors ✓

**Edge Cases (20% of tests):**
- Terminal states ✓
- Empty workflow ✓
- Concurrent updates ✓
- Health degradation ✓

**Performance (10% of tests):**
- State load <100ms ✓
- Transition <500ms ✓
- API response <100ms ✓

---

## COMPLEXITY & TIMELINE

### Estimated Complexity: LOW

**Reason:** No external dependencies, no distributed systems, no complex algorithms

- WorkflowEngine: 2-3 hours (file I/O + YAML)
- StateMachine: 1-2 hours (dict lookups)
- EventBus: 1-2 hours (in-memory pub/sub)
- AuditEngine: 2-3 hours (append-only log)
- RuntimeAPI: 3-4 hours (FastAPI endpoints)
- HealthManager: 2-3 hours (simple health checks)
- Tests: 8-10 hours (comprehensive coverage)
- **TOTAL: 19-27 hours** (2-3 days of coding)

### Timeline: 1 Week (5 days)

| Phase | Timeline | Deliverable |
|-------|----------|-------------|
| Design | Tue-Wed | Component designs, API spec |
| Implementation | Wed-Fri | Code (650 lines) |
| Testing | Fri | Tests (400+ lines) |
| Integration | Mon | DRT-001 working end-to-end |
| Staging | Tue-Wed | Helm chart, ops validation |
| **Complete** | **Wed EOD** | **Production-Ready MVP** |

---

## RISK REDUCTION

### Risks Eliminated (MVP Scope)

❌ **Removed:** Policy evaluation complexity (defer to DRT-006)  
❌ **Removed:** Metrics calculation complexity (defer to DRT-006)  
❌ **Removed:** Distributed locks (sequential execution OK)  
❌ **Removed:** Artifact registry (not needed yet)  
❌ **Removed:** Notification complexity (manual for now)  
❌ **Removed:** Recovery logic (MVP doesn't crash)  

### Risks Reduced

✅ **Complexity:** From 14 engines → 6 components  
✅ **Dependencies:** From 6 domains → 1 unit (self-contained)  
✅ **Timeline:** From 2 weeks → 1 week  
✅ **Testability:** From integration nightmare → simple unit tests  
✅ **Deployability:** From multi-component coordination → single Helm chart  

### Residual Risks (Low)

| Risk | Mitigation | Owner |
|------|-----------|-------|
| YAML write conflicts | File locking (atomic) | tech-lead |
| Audit log loss | Append-only journal | tech-lead |
| API validation gaps | Comprehensive tests | qa-engineer |
| Health check false negatives | Simple fast checks | devops |

---

## PRODUCTION READINESS CHECKLIST

By end of Week 1:

- [ ] 6 components implemented (650 lines code)
- [ ] 55+ tests passing (≥90% coverage)
- [ ] 4 API endpoints working
- [ ] Health endpoint responsive
- [ ] Helm chart deployable
- [ ] One complete capability lifecycle executable
- [ ] Zero manual state manipulation needed
- [ ] Audit trail complete and immutable
- [ ] Security review: zero findings
- [ ] Performance: all <500ms p95
- [ ] Operations runbook complete
- [ ] Staging validation: 24h stable

**Status:** ✅ READY_FOR_IMPLEMENTATION

---

## SUCCESS DEFINITION

**DRT-001 is successful when:**

1. ✅ One capability can execute a complete lifecycle (SPECIFICATION → CLOSED)
2. ✅ Transitions are automatic (no manual state edits)
3. ✅ State is persisted correctly (workflow.yaml)
4. ✅ Audit trail is complete (every action logged)
5. ✅ No external dependencies (self-contained)
6. ✅ Tests prove it works (55+ tests, ≥90% coverage)
7. ✅ Deployed to production (Helm chart, running on k8s)
8. ✅ Measurable: Runtime executes real capabilities

**Not about:** Framework completeness, theoretical correctness, all features

**Is about:** Shipping working software that executes capabilities

---

## NEXT PHASE UNBLOCKED

Once DRT-001 is deployed:

- ✅ DRT-002 can build Agent Dispatcher (has State Machine to call)
- ✅ DRT-003 can build Gate Evaluator (has Workflow state to read)
- ✅ DRT-004 can build full Audit Engine (has MVP to enhance)
- ✅ DRT-005 can build Recovery (has Audit to replay from)
- ✅ DRT-006 can build Policy + Metrics (has state to query)

**No blocking dependencies.** DRT-002 through DRT-006 ready to start Week 3.

---

## SUMMARY

| Aspect | Value |
|--------|-------|
| **Components** | 6 (Workflow, State Machine, EventBus, Audit, API, Health) |
| **Code** | 650 lines (Python) |
| **Tests** | 55+ tests, ≥90% coverage |
| **Timeline** | 1 week (5 days) |
| **Complexity** | LOW (file I/O, no distributed systems) |
| **Risk** | LOW (MVP scope, eliminated complex features) |
| **Production** | YES (deployable, operational, measurable) |
| **Value** | IMMEDIATE (executes real capabilities today) |

---

**STATUS: READY_FOR_IMPLEMENTATION**

**TIMELINE: Start 2026-07-14, Complete 2026-07-21**

**OWNER: tech-lead**

**MEASUREMENT: DRT-001 deployed, one complete capability executed automatically**
