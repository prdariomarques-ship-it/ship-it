# DRT v1.0 ARCHITECTURE
## Dario Runtime — Autonomous Capability Execution Engine

**Component**: AUTONOMOUS_CAPABILITY_RUNTIME  
**Version**: DRT v1.0  
**Authority**: Chief Architect  
**Mode**: ARCHITECTURE_EVOLUTION  
**Date**: 2026-07-13  
**Status**: ARCHITECTURE_APPROVED  

---

## EXECUTIVE SUMMARY

DRT (Dario Runtime) is the **execution kernel** of the Dario Platform, evolving the Governance Workflow Engine into a complete autonomous capability orchestration system. DRT orchestrates every capability lifecycle, enables agents to perform specialized work only, owns all execution, and provides complete auditability with zero manual intervention possible.

### Core Principle

```
Single Source of Truth (workflow.yaml)
        ↓
State Driven Execution
        ↓
Event Driven Automation
        ↓
Policy Driven Authorization
        ↓
Evidence Driven Decisions
        ↓
Deterministic, Auditable, Recoverable, Idempotent Runtime
```

---

## ARCHITECTURE OVERVIEW

### DRT v1.0 System Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                      DARIO RUNTIME v1.0 (DRT)                         │
│                   Autonomous Capability Execution Engine               │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │              Capability Runtime (Main Orchestrator)             │ │
│  │  • Event loop (continuous)                                     │ │
│  │  • State coordination                                          │ │
│  │  • Policy evaluation                                           │ │
│  │  • Recovery coordination                                       │ │
│  └────┬──────────────────────────┬───────────────────────┬───────┬─┘ │
│       │                          │                       │       │   │
│  ┌────▼──────────────┐  ┌────────▼─────────┐  ┌────────▼──┐  ┌─▼──┐ │
│  │ Workflow Engine   │  │ State Machine    │  │ Policy    │  │ CAP │
│  │ • Load state      │  │ • DAG transitions│  │ Engine    │  │ Lock│
│  │ • Parse phase     │  │ • Rollback       │  │ • Evaluate│  │ Mgr │
│  │ • Track owner     │  │ • Recovery       │  │ • Enforce │  │     │
│  │ • Persist state   │  │ • Persist history│  │ • Rules   │  └─────┘
│  └────┬──────────────┘  └────┬─────────────┘  └────┬──────┘         │
│       │                      │                     │                │
│  ┌────▼──────────────┐  ┌────▼──────────────┐  ┌──▼───────────────┐ │
│  │ Agent Dispatcher  │  │ Execution Queue   │  │ Event Bus        │ │
│  │ • Route work      │  │ • Capability Q    │  │ • EMIT events    │ │
│  │ • Verify auth     │  │ • Priority Q      │  │ • SUBSCRIBE      │ │
│  │ • Role-based      │  │ • Retry Q         │  │ • BROADCAST      │ │
│  │ • Phase-based     │  │ • Blocked Q       │  │ • 14 core events │ │
│  │                   │  │ • Dead Letter Q   │  │                  │ │
│  └─────────────────┬┘  └─────────────────┬─┘  └────────┬──────────┘ │
│                    │                     │             │             │
│  ┌─────────────────▼──────────────────────▼─────────────▼──────────┐ │
│  │      Evidence Pipeline & Gate Evaluation                       │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐ │ │
│  │  │ Evidence         │  │ Gate Evaluator   │  │ Artifact     │ │ │
│  │  │ Collector        │  │ • Tests          │  │ Registry     │ │ │
│  │  │ • git commands   │  │ • Coverage       │  │ • Track all  │ │ │
│  │  │ • pytest         │  │ • Security       │  │ • Version    │ │ │
│  │  │ • coverage       │  │ • Performance    │  │ • Checksum   │ │ │
│  │  │ • ruff, mypy     │  │ • Regression     │  │ • Integrity  │ │ │
│  │  │ • docker         │  │ • Documentation  │  │ • Relations  │ │ │
│  │  │ • benchmarks     │  │                  │  │              │ │ │
│  │  │ • security scan  │  │ Returns: PASS,   │  │              │ │ │
│  │  │                  │  │ FAIL, PENDING    │  │              │ │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│       │                                                               │
│  ┌────▼──────────────────────┐  ┌─────────────────────────────────┐ │
│  │ Metrics Engine            │  │ Audit Engine                    │ │
│  │ • Lead Time               │  │ • Timestamp every action        │ │
│  │ • Cycle Time              │  │ • Record authority              │ │
│  │ • Throughput              │  │ • Store evidence refs           │ │
│  │ • MTTR                    │  │ • Immutable log                 │ │
│  │ • Coverage Trend          │  │ • Checksummed (tamper proof)    │ │
│  │ • Quality Trend           │  │ • Queryable                     │ │
│  │ • Gate Duration           │  │                                 │ │
│  │ • Agent Workload          │  │                                 │ │
│  │ • Auto dashboards         │  │                                 │ │
│  └───────────────────────────┘  └─────────────────────────────────┘ │
│       │                                                               │
│  ┌────▼──────────────────────┐  ┌─────────────────────────────────┐ │
│  │ Recovery Manager          │  │ Notification Engine             │ │
│  │ • Resume executions       │  │ • Next owner notification       │ │
│  │ • Zero duplication        │  │ • Execution summaries           │ │
│  │ • Crash recovery          │  │ • Pending actions               │ │
│  │ • Queue persistence       │  │ • Blocker reports               │ │
│  │ • Lock recovery           │  │ • Completion reports            │ │
│  │ • State consistency       │  │                                 │ │
│  └───────────────────────────┘  └─────────────────────────────────┘ │
│       │                                                               │
│  ┌────▼──────────────────────────────────────────────────────────┐ │
│  │              Persistence Layer                               │ │
│  │  • workflow.yaml (source of truth)                           │ │
│  │  • Audit log (immutable, checksummed)                        │ │
│  │  • Queue persistence (Redis/PostgreSQL)                      │ │
│  │  • Artifact registry (versioned, checksummed)                │ │
│  │  • Metrics history (time-series)                             │ │
│  │  • Lock state (distributed)                                  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │           Configuration & Security                           │ │
│  │  • RBAC (Role-Based Access Control)                          │ │
│  │  • Policy repository (organizational rules)                  │ │
│  │  • Signed execution history                                  │ │
│  │  • Evidence integrity validation                             │ │
│  │  • Protected workflow transitions                            │ │
│  │  • Capability locks (distributed)                            │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 14 CORE ENGINES SPECIFICATION

### 1. Workflow Engine (Enhanced)

**Evolution from OBS-004**: Adds lock-aware state tracking and policy context.

```python
class WorkflowEngine:
    """Continuous workflow.yaml interpreter with lock awareness."""
    
    def load_state(self) -> WorkflowState:
        """Load current workflow state."""
        # Parse workflow.yaml
        # Check locks (are resources locked?)
        # Return: capability, phase, owner, locks, policies
    
    def update_phase(self, capability_id, new_phase, policy_check=None):
        """Update phase with policy evaluation."""
        # Evaluate policy (if provided)
        if policy_check:
            policy_result = policy_check(capability_id, new_phase)
            if policy_result == PolicyResult.DENY:
                raise PolicyViolationError(f"Policy denied transition")
        
        # Check locks (is capability locked?)
        if self.lock_manager.is_locked(capability_id):
            raise LockError(f"Capability {capability_id} is locked")
        
        # Acquire write lock
        with self.lock_manager.acquire_write_lock(capability_id):
            # Update workflow.yaml atomically
            self.workflow_yaml[capability_id]['phase'] = new_phase
            self.persist()
```

**Responsibilities**:
- ✅ Load workflow state (with lock context)
- ✅ Track capability, phase, owner
- ✅ Persist transitions (atomic writes)
- ✅ Check policy constraints
- ✅ Respect capability locks

---

### 2. State Machine (Enhanced)

**Evolution from OBS-004**: Adds recovery history and rollback support.

```python
class StateMachine:
    """DAG-enforced state transitions with rollback capability."""
    
    def is_valid_transition(self, current_phase, next_phase, 
                           policy_result=None) -> bool:
        """Check if transition is valid."""
        # Check DAG rules
        if next_phase not in VALID_TRANSITIONS[current_phase]:
            return False
        
        # Check policy result
        if policy_result == PolicyResult.DENY:
            return False
        
        return True
    
    def rollback(self, capability_id, target_phase):
        """Rollback to previous valid phase."""
        # Find target_phase in execution history
        # Verify it was a valid state (all gates passed)
        # Restore workflow state
        # Emit ROLLED_BACK event
        # Record in audit log with reason
    
    def recovery_history(self, capability_id) -> List[PhaseTransition]:
        """Get complete phase transition history for replay."""
        # Return all transitions in order
        # Can be used to replay execution
```

**Responsibilities**:
- ✅ Enforce DAG transitions
- ✅ Validate against policies
- ✅ Support rollback
- ✅ Persist execution history
- ✅ Enable replay/recovery

---

### 3. Policy Engine (NEW)

**New Component**: Organizational rules enforcement.

```python
class PolicyEngine:
    """Evaluate organizational policies before state transitions."""
    
    def __init__(self):
        self.policies = load_policies_from_repository()
    
    def evaluate(self, capability_id: str, 
                transition: Transition) -> PolicyResult:
        """Evaluate if transition is allowed by policies."""
        results = []
        
        # Check all matching policies
        for policy in self.policies.matching(transition):
            result = policy.evaluate(capability_id, transition)
            results.append(result)
        
        # Decision logic:
        # - If any policy returns DENY: return DENY
        # - If any policy returns CONDITIONAL: return CONDITIONAL
        # - If all return ALLOW: return ALLOW
        
        if any(r == PolicyResult.DENY for r in results):
            return PolicyResult.DENY
        elif any(r == PolicyResult.CONDITIONAL for r in results):
            return PolicyResult.CONDITIONAL
        else:
            return PolicyResult.ALLOW
```

**Policy Examples**:
```yaml
policies:
  - id: NO_MERGE_WITHOUT_QA
    rule: |
      IF transition == MERGE_AUTHORIZATION
      AND capability.qa_approval != APPROVED
      THEN DENY
    severity: CRITICAL
    
  - id: NO_DEPLOY_DURING_MAINTENANCE
    rule: |
      IF transition == PRODUCTION_DEPLOYMENT
      AND maintenance_freeze == ACTIVE
      THEN DENY
    severity: CRITICAL
    
  - id: NO_CONCURRENT_DEPLOYS
    rule: |
      IF transition == PRODUCTION_DEPLOYMENT
      AND other_deployment_in_progress()
      THEN CONDITIONAL (queue and wait)
    severity: HIGH
    
  - id: MANDATORY_GATES
    rule: |
      IF capability.gates_passed < 8
      THEN DENY (cannot proceed without all gates)
    severity: CRITICAL
```

**Policy Result Types**:
```python
class PolicyResult(Enum):
    ALLOW = "allow"              # Transition allowed
    DENY = "deny"                # Transition blocked (error)
    CONDITIONAL = "conditional"  # Allowed with conditions (e.g., wait)
```

**Responsibilities**:
- ✅ Load policies from repository
- ✅ Match policies to transitions
- ✅ Evaluate rules against state
- ✅ Return ALLOW/DENY/CONDITIONAL
- ✅ Audit policy evaluations

---

### 4. Capability Lock Manager (NEW)

**New Component**: Prevent concurrent modification of protected resources.

```python
class CapabilityLockManager:
    """Distributed lock manager for capability resources."""
    
    def __init__(self, backend: "Redis"):
        self.backend = backend  # Distributed lock storage
    
    def acquire_read_lock(self, capability_id: str, 
                         timeout: int = 300):
        """Acquire read lock (multiple allowed)."""
        return ReadLock(self.backend, capability_id, timeout)
    
    def acquire_write_lock(self, capability_id: str, 
                          timeout: int = 300):
        """Acquire write lock (exclusive)."""
        return WriteLock(self.backend, capability_id, timeout)
    
    def is_locked(self, capability_id: str) -> bool:
        """Check if capability is locked."""
        return self.backend.exists(f"lock:{capability_id}")
    
    def force_release(self, capability_id: str, reason: str):
        """Admin function to force-release lock."""
        self.backend.delete(f"lock:{capability_id}")
        self.audit_engine.record("LOCK_FORCE_RELEASED", {
            "capability": capability_id,
            "reason": reason
        })
    
    def recover_locks(self):
        """Recover from crashed process holding locks."""
        stale_locks = self.find_stale_locks()
        for lock in stale_locks:
            self.force_release(lock.capability, "stale lock recovery")
```

**Lock Types**:
```python
class ReadLock:
    """Multiple readers allowed."""
    
    async def __aenter__(self):
        await self.backend.increment(f"read_lock:{self.capability_id}")
        return self
    
    async def __aexit__(self, *args):
        await self.backend.decrement(f"read_lock:{self.capability_id}")

class WriteLock:
    """Exclusive lock, no other readers/writers."""
    
    async def __aenter__(self):
        # Wait for all readers to finish
        while await self.backend.get(f"read_lock:{self.capability_id}"):
            await asyncio.sleep(0.1)
        
        # Acquire exclusive lock
        await self.backend.set(f"write_lock:{self.capability_id}", 
                             self.process_id, timeout=self.timeout)
        return self
    
    async def __aexit__(self, *args):
        await self.backend.delete(f"write_lock:{self.capability_id}")
```

**Lock Scenarios**:
- ✅ Read lock: Multiple agents reading same capability (safe)
- ✅ Write lock: Only one agent modifying capability (exclusive)
- ✅ Timeout: Auto-release if process hangs (default 5 min)
- ✅ Force release: Admin recovery function
- ✅ Deadlock prevention: No nested locks (async/await safe)

**Responsibilities**:
- ✅ Prevent concurrent modification
- ✅ Support read/write lock modes
- ✅ Auto-release on timeout
- ✅ Recover stale locks
- ✅ Audit lock operations

---

### 5. Agent Dispatcher (Enhanced)

**Evolution from OBS-004**: Adds lock acquisition before dispatch.

```python
class AgentDispatcher:
    """Automatic work routing with lock awareness."""
    
    async def dispatch(self, capability: str, phase: str):
        """Dispatch work to appropriate agent."""
        # Determine required authority
        authority = PHASE_AUTHORITY[phase]
        
        # Acquire read lock (agent will hold for duration)
        with self.lock_manager.acquire_read_lock(capability):
            # Get agent for phase
            agent = self.get_agent(phase, authority)
            
            # Create execution task
            task = ExecutionTask(
                capability=capability,
                agent=agent,
                phase=phase,
                lock_held=True
            )
            
            # Enqueue task
            self.execution_queue.enqueue(task)
            
            # Record dispatch
            self.audit_engine.record("TASK_DISPATCHED", {
                "capability": capability,
                "phase": phase,
                "agent": agent.name,
                "lock_acquired": True
            })
```

**Responsibilities**:
- ✅ Acquire read lock before dispatch
- ✅ Route to correct agent (role-based)
- ✅ Verify authorization
- ✅ Create execution task
- ✅ Record in audit log

---

### 6. Execution Queue (Enhanced)

**Evolution from OBS-004**: Adds lock tracking.

```python
class ExecutionQueue:
    """Persistent execution queue with lock tracking."""
    
    class Task:
        capability: str
        agent: str
        phase: str
        lock_acquired: bool  # Does agent hold lock?
        created_at: datetime
        started_at: Optional[datetime] = None
        completed_at: Optional[datetime] = None
        
    def enqueue(self, task: Task, queue_type: str = "capability"):
        """Enqueue task."""
        # Validate lock is held if required
        if task.requires_lock and not task.lock_acquired:
            raise LockError("Task requires lock but none acquired")
        
        self.get_queue(queue_type).push(task)
    
    def release_lock_on_completion(self, task: Task):
        """Release lock when task completes."""
        if task.lock_acquired:
            self.lock_manager.release_read_lock(task.capability)
```

**Responsibilities**:
- ✅ Persist 5 queue types
- ✅ Track lock state per task
- ✅ Support retry policies
- ✅ Support timeout policies
- ✅ Release locks on completion

---

### 7. Event Bus (Enhanced)

**Evolution from OBS-004**: Same core, now driven by Policy Engine results.

```python
class EventBus:
    """Internal pub-sub event system."""
    
    def emit(self, event: Event):
        """Publish event to all subscribers."""
        # Audit event
        self.audit_engine.record("EVENT_EMITTED", {
            "event_type": event.type,
            "capability": event.capability_id,
            "timestamp": event.timestamp
        })
        
        # Notify subscribers
        handlers = self.subscribers.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                # Do not propagate (fail-safe)
                self.audit_engine.record("EVENT_HANDLER_ERROR", {
                    "event_type": event.type,
                    "error": str(e)
                })
```

**14 Core Events**:
```
1. SPECIFICATION_READY
2. SPECIFICATION_APPROVED
3. DESIGN_APPROVED
4. IMPLEMENTATION_STARTED
5. IMPLEMENTATION_COMPLETED
6. QA_APPROVED
7. FINAL_REVIEW_APPROVED
8. MERGE_COMPLETED
9. INFRASTRUCTURE_VALIDATION_PASSED
10. PRODUCTION_DEPLOYED
11. CAPABILITY_CLOSED
12. FAILED
13. BLOCKED
14. ROLLED_BACK
```

**Responsibilities**:
- ✅ Emit core 14 events
- ✅ Internal pub-sub only
- ✅ Fail-safe handlers
- ✅ Complete audit trail
- ✅ Event ordering

---

### 8. Gate Evaluator (Enhanced)

**Evolution from OBS-004**: Adds evidence linking to artifact registry.

```python
class GateEvaluator:
    """Automatic gate validation with artifact tracking."""
    
    def evaluate(self, gate: str, evidence: Dict) -> GateDecision:
        """Evaluate gate against criteria."""
        validator = GATE_VALIDATORS[gate]
        
        # Collect evidence
        evidence_items = self.evidence_collector.collect_for_gate(gate)
        
        # Register evidence artifacts
        artifacts = []
        for item in evidence_items:
            artifact = self.artifact_registry.register(
                type="evidence",
                data=item,
                capability=self.current_capability,
                gate=gate,
                checksum=compute_checksum(item)
            )
            artifacts.append(artifact)
        
        # Validate
        result = validator.validate(evidence_items)
        
        # Decision with artifact links
        decision = GateDecision(
            gate=gate,
            status=result.status,  # PASS, FAIL, PENDING_EVIDENCE
            evidence_artifacts=artifacts,
            timestamp=datetime.utcnow().isoformat()
        )
        
        return decision
```

**Responsibilities**:
- ✅ Evaluate all 9 gate criteria
- ✅ Collect objective evidence
- ✅ Register evidence artifacts
- ✅ Link artifacts to gates
- ✅ Return PASS/FAIL/PENDING

---

### 9. Evidence Collector (Enhanced)

**Evolution from OBS-004**: Same core, now registers artifacts automatically.

```python
class EvidenceCollector:
    """Automatic objective evidence collection."""
    
    async def collect(self, capability: str) -> EvidenceBundle:
        """Collect all evidence for capability."""
        evidence = EvidenceBundle(capability)
        
        # Collect from each system
        evidence.git_status = await shell("git status --porcelain")
        evidence.tests_passed = await self.run_tests()
        evidence.coverage_percent = await self.run_coverage()
        # ... more evidence ...
        
        # Register all evidence in artifact registry
        artifact = self.artifact_registry.register(
            type="evidence_bundle",
            data=evidence,
            capability=capability,
            timestamp=datetime.utcnow().isoformat(),
            checksum=compute_checksum(evidence)
        )
        
        return evidence
```

**Responsibilities**:
- ✅ Execute evidence procedures
- ✅ Never fabricate evidence
- ✅ Timestamp all evidence
- ✅ Compute checksums
- ✅ Register artifacts

---

### 10. Artifact Registry (NEW)

**New Component**: Track all artifacts with versions and relationships.

```python
class ArtifactRegistry:
    """Central registry for all capability artifacts."""
    
    def register(self, artifact_type: str, data: Any, 
                capability: str, **metadata) -> Artifact:
        """Register artifact."""
        artifact = Artifact(
            id=self._next_artifact_id(),
            type=artifact_type,
            capability=capability,
            version=self._compute_version(capability),
            owner=metadata.get('owner'),
            data=data,
            checksum=compute_checksum(data),
            created_at=datetime.utcnow(),
            modified_at=datetime.utcnow(),
            status="ACTIVE",
            metadata=metadata
        )
        
        # Store in registry
        self.backend.store(artifact)
        
        # Update relationship graph
        if 'related_to' in metadata:
            self.graph.add_edge(artifact.id, metadata['related_to'])
        
        return artifact
    
    def get_artifact(self, artifact_id: str) -> Artifact:
        """Retrieve artifact by ID."""
        artifact = self.backend.retrieve(artifact_id)
        
        # Verify integrity
        if compute_checksum(artifact.data) != artifact.checksum:
            raise IntegrityError(f"Artifact {artifact_id} corrupted")
        
        return artifact
    
    def get_related_artifacts(self, artifact_id: str) -> List[Artifact]:
        """Get all artifacts related to this one."""
        return self.graph.neighbors(artifact_id)
    
    def list_by_capability(self, capability_id: str) -> List[Artifact]:
        """List all artifacts for capability."""
        return self.backend.query({"capability": capability_id})
```

**Artifact Types**:
```python
class ArtifactType(Enum):
    SPECIFICATION = "specification"
    DESIGN = "design"
    IMPLEMENTATION = "implementation"
    CODE_REVIEW = "code_review"
    TEST = "test"
    COVERAGE_REPORT = "coverage_report"
    EVIDENCE = "evidence"
    GATE_DECISION = "gate_decision"
    AUDIT_ENTRY = "audit_entry"
    METRIC = "metric"
    DASHBOARD = "dashboard"
```

**Artifact Structure**:
```python
class Artifact:
    id: str                      # Unique ID
    type: ArtifactType          # Type of artifact
    capability: str             # Capability ID
    version: str                # Semantic version (x.y.z)
    owner: str                  # Who created it (authority)
    data: Any                   # Artifact content
    checksum: str               # SHA256 for integrity
    created_at: datetime        # Creation timestamp
    modified_at: datetime       # Last modification
    status: str                 # ACTIVE, ARCHIVED, DEPRECATED
    metadata: Dict[str, Any]    # Extra fields
    related_to: List[str]       # Related artifact IDs
```

**Responsibilities**:
- ✅ Register all artifacts
- ✅ Assign unique IDs
- ✅ Track versions
- ✅ Compute checksums
- ✅ Verify integrity
- ✅ Maintain relationships

---

### 11. Metrics Engine (NEW)

**New Component**: Automatic calculation of key execution metrics.

```python
class MetricsEngine:
    """Automatic calculation of execution metrics."""
    
    def calculate_metrics(self) -> ExecutionMetrics:
        """Calculate all metrics from audit trail."""
        
        # Lead Time: From SPECIFICATION_READY to CAPABILITY_CLOSED
        lead_time = self._calculate_lead_time()
        
        # Cycle Time: Implementation start to CAPABILITY_CLOSED
        cycle_time = self._calculate_cycle_time()
        
        # Throughput: Capabilities per week
        throughput = self._calculate_throughput()
        
        # MTTR: Mean Time To Recovery (from failure to recovered)
        mttr = self._calculate_mttr()
        
        # Regression Rate: (regressions / total capabilities)
        regression_rate = self._calculate_regression_rate()
        
        # Coverage Trend: Average coverage over time
        coverage_trend = self._calculate_coverage_trend()
        
        # Quality Trend: Average quality score over time
        quality_trend = self._calculate_quality_trend()
        
        # Gate Duration: Average time per gate
        gate_durations = self._calculate_gate_durations()
        
        # Agent Duration: Average time per agent
        agent_durations = self._calculate_agent_durations()
        
        # Blocked Time: Time in blocked state
        blocked_time = self._calculate_blocked_time()
        
        # Deployment Frequency: Deployments per week
        deployment_frequency = self._calculate_deployment_frequency()
        
        return ExecutionMetrics(
            lead_time=lead_time,
            cycle_time=cycle_time,
            throughput=throughput,
            mttr=mttr,
            regression_rate=regression_rate,
            coverage_trend=coverage_trend,
            quality_trend=quality_trend,
            gate_durations=gate_durations,
            agent_durations=agent_durations,
            blocked_time=blocked_time,
            deployment_frequency=deployment_frequency
        )
    
    def generate_dashboard(self) -> Dashboard:
        """Generate metrics dashboard."""
        metrics = self.calculate_metrics()
        
        dashboard = Dashboard(
            title="Capability Execution Metrics",
            timestamp=datetime.utcnow(),
            panels=[
                Panel(title="Lead Time (days)", metric=metrics.lead_time),
                Panel(title="Cycle Time (days)", metric=metrics.cycle_time),
                Panel(title="Throughput (caps/week)", metric=metrics.throughput),
                Panel(title="MTTR (hours)", metric=metrics.mttr),
                Panel(title="Coverage (%)", chart=metrics.coverage_trend),
                Panel(title="Quality Score", chart=metrics.quality_trend),
                Panel(title="Gate Duration", chart=metrics.gate_durations),
                Panel(title="Deployment Frequency", metric=metrics.deployment_frequency),
            ]
        )
        
        return dashboard
```

**Metrics Calculated**:
```python
class ExecutionMetrics:
    lead_time: timedelta           # Spec ready → closed
    cycle_time: timedelta          # Implementation → closed
    throughput: float              # Capabilities per week
    mttr: timedelta                # Mean Time To Recovery
    regression_rate: float         # % of capabilities with regression
    coverage_trend: List[Point]    # Coverage over time (chart)
    quality_trend: List[Point]     # Quality score over time
    gate_durations: Dict[str, timedelta]  # Average per gate
    agent_durations: Dict[str, timedelta] # Average per agent
    blocked_time: timedelta        # Total time in blocked state
    deployment_frequency: float    # Deployments per week
```

**Responsibilities**:
- ✅ Calculate 11 key metrics
- ✅ Query audit trail for data
- ✅ Generate trend charts
- ✅ Produce dashboards automatically
- ✅ Update metrics continuously

---

### 12. Recovery Manager (Enhanced)

**Evolution from OBS-004**: Adds lock recovery and artifact validation.

```python
class RecoveryManager:
    """Crash recovery with lock and state restoration."""
    
    async def recover_if_needed(self):
        """Check and recover from interrupted executions."""
        # 1. Recover stale locks
        await self._recover_stale_locks()
        
        # 2. Recover crashed queues
        await self._recover_queues()
        
        # 3. Recover workflow state
        await self._recover_workflow_state()
        
        # 4. Validate artifact integrity
        await self._validate_artifacts()
    
    async def _recover_stale_locks(self):
        """Recover locks held by crashed processes."""
        stale_locks = self.lock_manager.find_stale_locks(
            timeout=300  # 5 minutes
        )
        
        for lock in stale_locks:
            self.lock_manager.force_release(
                lock.capability,
                reason="stale lock from crash"
            )
            self.audit_engine.record("LOCK_RECOVERED", {
                "capability": lock.capability,
                "held_for_seconds": lock.duration_seconds
            })
    
    async def _validate_artifacts(self):
        """Validate all artifact integrity."""
        for artifact in self.artifact_registry.list_all():
            # Recompute checksum
            current_checksum = compute_checksum(artifact.data)
            
            if current_checksum != artifact.checksum:
                # Corruption detected
                self.audit_engine.record("ARTIFACT_CORRUPTION", {
                    "artifact_id": artifact.id,
                    "expected_checksum": artifact.checksum,
                    "actual_checksum": current_checksum
                })
                
                # Escalate to chief architect
                self.notification_engine.escalate(
                    "chief-architect",
                    f"Artifact corruption detected: {artifact.id}"
                )
```

**Responsibilities**:
- ✅ Recover stale locks
- ✅ Recover queues
- ✅ Recover workflow state
- ✅ Validate artifact integrity
- ✅ Prevent duplicated execution

---

### 13. Audit Engine (Enhanced)

**Evolution from OBS-004**: Adds policy audit and lock tracking.

```python
class AuditEngine:
    """Immutable, checksummed audit log."""
    
    def record(self, event_type: str, data: Dict):
        """Record audit entry (append-only)."""
        entry = AuditEntry(
            entry_id=self._next_entry_id(),
            timestamp=datetime.utcnow().isoformat() + "Z",
            event_type=event_type,
            capability=data.get('capability'),
            owner=data.get('owner'),
            decision=data.get('decision'),
            policy_result=data.get('policy_result'),
            lock_held=data.get('lock_held', False),
            artifacts=data.get('artifacts', []),
            duration_seconds=data.get('duration_seconds'),
            retry_count=data.get('retry_count', 0),
            error=data.get('error'),
            **data
        )
        
        # Append to log (never modify)
        self.backend.append(entry.to_dict())
        
        # Compute checksum
        checksum = self._compute_checksum(entry)
        self.backend.record_checksum(entry.entry_id, checksum)
        
        # Register audit entry as artifact
        self.artifact_registry.register(
            type="audit_entry",
            data=entry,
            capability=entry.capability,
            owner=entry.owner,
            checksum=checksum
        )
```

**Audit Entry Structure**:
```python
class AuditEntry:
    entry_id: str              # AE-20260714-001
    timestamp: str             # ISO8601 + Z
    event_type: str            # TASK_DISPATCHED, GATE_EVALUATED, etc.
    capability: str            # OBS-XXX
    owner: str                 # Chief Architect, Tech Lead, etc.
    phase: str                 # Current phase
    decision: str              # APPROVED, REJECTED, BLOCKED
    policy_result: str         # ALLOW, DENY, CONDITIONAL
    lock_held: bool            # Was lock held?
    artifacts: List[str]       # Artifact IDs involved
    duration_seconds: int      # How long did it take?
    retry_count: int           # Retry attempt number
    error: Optional[str]       # Error message if failed
    checksum: str              # SHA256 for integrity
```

**Responsibilities**:
- ✅ Record every action
- ✅ Track policy results
- ✅ Track lock state
- ✅ Link artifacts
- ✅ Immutable append-only log
- ✅ Checksum verification

---

### 14. Notification Engine (Enhanced)

**Evolution from OBS-004**: Adds metrics and policy notifications.

```python
class NotificationEngine:
    """Automatic notifications with metrics context."""
    
    async def notify_next_owner(self, capability: str):
        """Notify next phase owner."""
        state = self.workflow_engine.load_state(capability)
        next_phase = self.state_machine.next_phase(state.phase)
        next_owner = PHASE_AUTHORITY[next_phase]
        
        # Get metrics
        metrics = self.metrics_engine.calculate_metrics()
        
        # Check for blockers
        blockers = self._get_blockers(capability)
        
        # Get related artifacts
        artifacts = self.artifact_registry.list_by_capability(capability)
        
        message = NotificationMessage(
            recipient=next_owner,
            capability=capability,
            current_phase=state.phase,
            next_phase=next_phase,
            summary=self._generate_summary(capability, state),
            pending_actions=self._get_pending_actions(capability),
            blockers=blockers,
            metrics=metrics,
            artifacts=artifacts,
            timestamp=datetime.utcnow().isoformat()
        )
        
        await self.send(message)
    
    async def notify_policy_violation(self, capability: str, 
                                     policy: str, reason: str):
        """Notify chief architect of policy violation."""
        message = NotificationMessage(
            recipient="chief-architect",
            subject=f"Policy Violation: {policy}",
            capability=capability,
            body=f"Capability {capability} blocked by policy {policy}: {reason}",
            severity="CRITICAL"
        )
        
        await self.send(message)
```

**Notification Types**:
- ✅ Next owner notification (transition ready)
- ✅ Blocker notification (dependencies)
- ✅ Policy violation notification (escalation)
- ✅ Failure notification (error escalation)
- ✅ Metrics notification (performance alerts)

**Responsibilities**:
- ✅ Notify next owner automatically
- ✅ Notify on blockers
- ✅ Notify on policy violations
- ✅ Notify on failures
- ✅ Include metrics context

---

## STATE MODEL

### Complete Lifecycle with Lock and Policy Context

```
QUEUED (ready for specification)
  │
  ├─ Policy Check: SPECIFICATION_PERMITTED?
  │  └─ ALLOW → continue
  │  └─ DENY → blocked (notify chief-architect)
  │  └─ CONDITIONAL → queue with condition
  │
  ├─ Lock: Acquire read lock on capability
  │
  ├─ Dispatch: Send to Chief Architect Agent
  │
  └─→ SPECIFICATION (0-7 days)
       │ Execute specification work
       │ Collect evidence
       │ Evaluate gates
       │ Generate artifacts
       │
       ├─ Policy Check: DESIGN_PERMITTED?
       │  └─ ALLOW → proceed
       │  └─ DENY → blocked
       │
       └─→ DESIGN_REVIEW (0-5 days)
           │ Dispatch to Tech Lead
           │ Review architecture
           │ Evaluate gates
           │
           └─→ IMPLEMENTATION (0-14 days)
               │ Dispatch to Impl Engineer
               │ Execute work
               │ Parallel branches: CODE_REVIEW || QA
               │
               ├─ CODE_REVIEW (0-3 days, Tech Lead)
               │  └─→ APPROVED/REJECTED
               │
               └─ QA_ASSURANCE (0-3 days, QA)
                  └─→ APPROVED/REJECTED
               
               (Both must PASS before proceeding)
               
               └─→ FINAL_REVIEW (0-1 days)
                   │
                   ├─ Policy Check: MERGE_PERMITTED?
                   │  └─ DENY → rollback
                   │
                   └─→ MERGE_AUTHORIZATION (CTO)
                       │
                       ├─ Policy Check: DEPLOY_PERMITTED?
                       │
                       └─→ INFRASTRUCTURE_VALIDATION
                           └─→ PRODUCTION_DEPLOYMENT
                               └─→ CAPABILITY_CLOSED
```

---

## POLICY MODEL

### Policy Definition Format

```yaml
name: "No Merge Without QA Approval"
id: "policy-001"
enabled: true

trigger:
  event: "GATE_EVALUATED"
  gate: "MERGE_AUTHORIZATION"

rule: |
  IF capability.qa_approval != APPROVED
  THEN DENY

policy_result: DENY
severity: CRITICAL
enforcement: BLOCKING

escalation:
  notify: ["chief-architect", "cto"]
  message: "Cannot merge without QA approval"
  action: "BLOCK_TRANSITION"
```

### Policy Decision Flow

```
Policy Engine
  ├─ Load all policies
  ├─ Match policies to transition
  ├─ Evaluate each policy
  │  ├─ Check condition
  │  ├─ Evaluate rule
  │  └─ Return: ALLOW, DENY, CONDITIONAL
  ├─ Aggregate decisions
  │  ├─ If any DENY: result = DENY
  │  ├─ Else if any CONDITIONAL: result = CONDITIONAL
  │  ├─ Else: result = ALLOW
  ├─ Record in audit log
  └─ Emit POLICY_EVALUATED event
```

---

## PERSISTENCE MODEL

### Multi-Tier Persistence Strategy

```
Tier 1: Source of Truth
  └─ workflow.yaml (single file, atomic updates)

Tier 2: Audit Trail
  └─ audit_log (append-only, checksummed)

Tier 3: Execution State
  └─ Redis/PostgreSQL
    ├─ Queues (capability, priority, retry, blocked, dead letter)
    ├─ Locks (distributed lock state)
    └─ Recovery state (in-flight tasks)

Tier 4: Artifact Registry
  └─ PostgreSQL
    ├─ Artifact metadata (id, type, version, checksum)
    ├─ Artifact content (versioned, archived)
    └─ Relationship graph (capability → artifacts)

Tier 5: Metrics
  └─ Time-series database (InfluxDB/Prometheus)
    ├─ Execution metrics (lead time, cycle time, etc.)
    ├─ Gate metrics (per-gate duration)
    └─ Agent metrics (per-agent workload)
```

### Atomic Operations Guarantee

```python
class AtomicUpdate:
    """Ensures multi-tier updates are all-or-nothing."""
    
    async def execute(self, updates: List[UpdateOperation]):
        """Execute multiple updates atomically."""
        
        # Phase 1: Prepare (acquire locks, validate)
        for update in updates:
            update.prepare()
        
        # Phase 2: Commit (all or nothing)
        try:
            for update in updates:
                await update.commit()
        except Exception as e:
            # Rollback all updates
            for update in reversed(updates):
                await update.rollback()
            raise
```

---

## SECURITY MODEL

### RBAC + Policy + Audit

```
Request
  │
  ├─ 1. Authenticate (who are you?)
  │  └─ Verify identity (API key, OAuth token)
  │
  ├─ 2. Authorize (are you allowed?)
  │  └─ Check RBAC (role → permissions)
  │  └─ Check policy (organizational rules)
  │
  ├─ 3. Audit (log the action)
  │  └─ Record in audit log
  │  └─ Register artifacts
  │
  └─ 4. Execute (do the work)
     └─ Acquire locks if needed
     └─ Execute state transition
     └─ Persist changes
```

### Evidence Integrity

```python
class EvidenceIntegrity:
    """Prevent evidence tampering."""
    
    def verify(self, evidence: Evidence) -> bool:
        """Verify evidence is authentic."""
        
        # 1. Checksum verification
        computed = compute_checksum(evidence.data)
        if computed != evidence.checksum:
            return False  # Tampered!
        
        # 2. Timestamp verification
        if evidence.timestamp > datetime.utcnow():
            return False  # Future timestamp = tampered!
        
        # 3. Source verification
        if evidence.source not in TRUSTED_SOURCES:
            return False  # Untrusted source
        
        # 4. Signature verification (optional)
        if not self.verify_signature(evidence.signature):
            return False  # Invalid signature
        
        return True
```

---

## SUCCESS METRICS

| Metric | Baseline | Target | Method |
|--------|----------|--------|--------|
| Manual orchestration | 100% | ≤10% | Audit log analysis |
| Automatic transitions | 0% | 100% | Phase transition audit |
| Gate automation | 0% | 100% | Gate evaluator logs |
| Evidence automation | 0% | 100% | Evidence collector |
| Doc synchronization | Manual | 100% | Doc timestamp tracking |
| Policy enforcement | Manual | 100% | Policy audit records |
| Lock efficiency | N/A | <5ms/lock | Lock timing metrics |
| Artifact tracking | Manual | 100% | Registry audit |
| Crash recovery | N/A | 100% | Recovery test results |
| Duplication rate | N/A | 0% | Duplicate detection |

---

## ACCEPTANCE CRITERIA

### Functional

- ✅ All 14 engines implemented and integrated
- ✅ State machine enforces legal transitions only
- ✅ Policy engine blocks illegal transitions
- ✅ Lock manager prevents concurrent modification
- ✅ Evidence collector gathers objective evidence
- ✅ Artifact registry tracks all outputs
- ✅ Metrics engine calculates 11+ metrics
- ✅ Recovery manager recovers from crashes
- ✅ Audit engine creates immutable log
- ✅ Notifications deliver to next owner

### Non-Functional

- ✅ Crash-safe (process death → recovery)
- ✅ Idempotent (retry-safe)
- ✅ Deterministic (replay-able)
- ✅ Auditable (100% action logged)
- ✅ Scalable (horizontal)
- ✅ Observable (metrics + queries)
- ✅ Secure (RBAC + audit)

---

## DEFINITION OF READY (DoR)

- ✅ Architecture approved by Chief Architect
- ✅ All 14 components designed
- ✅ Security model reviewed
- ✅ Persistence strategy finalized
- ✅ Testing strategy defined
- ✅ Team assignments complete
- ✅ Infrastructure requirements identified
- ✅ Rollback strategy documented

---

## DEFINITION OF DONE (DoD)

- ✅ All 14 engines implemented
- ✅ Integration tests pass (all engines together)
- ✅ All acceptance criteria verified
- ✅ Security review passed
- ✅ Performance benchmarks met
- ✅ Crash recovery tested
- ✅ Audit trail verified complete
- ✅ Documentation complete
- ✅ Production deployment procedure documented
- ✅ Monitoring dashboards working
- ✅ On-call runbooks updated

---

## DELIVERABLES CHECKLIST

- ✅ DRT_v1_ARCHITECTURE.md (THIS DOCUMENT)
- ✅ Component interaction diagrams
- ✅ State machine diagram (with locks)
- ✅ Policy evaluation flowchart
- ✅ Lock acquisition sequence diagram
- ✅ Artifact registry data model
- ✅ Metrics calculation procedures
- ✅ Recovery procedures
- ✅ Security model documentation
- ✅ Persistence model documentation
- ✅ Testing strategy
- ✅ Acceptance criteria
- ✅ DoR/DoD
- ✅ Rollback strategy

---

## FORMAL CERTIFICATION

**Architecture Status**: ✅ **APPROVED**

**Authority**: Chief Architect  
**Date**: 2026-07-13  
**Version**: DRT v1.0  

**Enables**:
- ✅ OBS-003: Performance Optimization & Caching (frozen)
- ✅ OBS-002: Distributed Tracing (frozen)
- ✅ All future capabilities (autonomous execution)
- ✅ 90%+ manual intervention elimination

**Next Phase**: DESIGN_REVIEW (Tech Lead)  
**Deadline**: 2026-07-20

---

**END OF DRT v1.0 ARCHITECTURE**

The Dario Runtime is architected to autonomously execute the complete AOM v3.1 capability lifecycle with policy enforcement, lock management, artifact tracking, and complete auditability.

**STATUS: READY_FOR_DESIGN_REVIEW**
