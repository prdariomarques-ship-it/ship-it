# DRT RUNTIME COMPONENT INTERFACE
## Standard Contract for All Runtime Modules

**Version**: DRT v1.0  
**Authority**: Chief Architect  
**Date**: 2026-07-13  
**Classification**: Architecture Standard  

---

## EXECUTIVE SUMMARY

The RuntimeComponent interface defines the standard contract that **every** component in the Dario Runtime must implement. This ensures:

- ✅ **Independent deployability** (can be deployed in any order)
- ✅ **Independent testability** (can be tested in isolation)
- ✅ **Independent replaceability** (can swap implementations)
- ✅ **Loose coupling** (no direct dependencies)
- ✅ **Interface-driven** (communicate via contracts only)
- ✅ **Event-driven** (reactive, not imperative)

---

## CORE PRINCIPLE

```
Every component is a black box.

No component may know another component's internals.

All communication flows through standardized interfaces, events, and contracts.

Components interact as peers via the Event Bus.

No hierarchical dependencies allowed.
```

---

## RUNTIME COMPONENT INTERFACE

### Base Interface

```python
from abc import ABC, abstractmethod
from enum import Enum
from datetime import datetime
from typing import Dict, Any, Optional, List
import asyncio

class ComponentState(str, Enum):
    """Lifecycle states for runtime components."""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    RECOVERING = "recovering"
    SHUTDOWN = "shutdown"
    ERROR = "error"

class HealthStatus(str, Enum):
    """Component health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

class ComponentMetrics:
    """Standard metrics every component exposes."""
    initialized_at: datetime
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    error_count: int
    restart_count: int
    uptime_seconds: float
    state: ComponentState
    health: HealthStatus
    custom_metrics: Dict[str, Any]  # Component-specific

class RuntimeComponent(ABC):
    """
    Standard interface for all Dario Runtime components.
    
    Every component SHALL implement these methods.
    Components communicate ONLY through events and interfaces.
    No direct component-to-component dependencies allowed.
    """
    
    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """
        Initialize component with configuration.
        
        Called once at startup, before start().
        
        Args:
            config: Component configuration dictionary
            
        Raises:
            InitializationError: If initialization fails
            
        State Transition:
            UNINITIALIZED → INITIALIZING → INITIALIZED
            
        Guarantees:
            - Idempotent (safe to call multiple times)
            - No side effects if already initialized
            - All internal state prepared
        """
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """
        Start the component.
        
        Called after initialize(), begins active work.
        Component enters event-driven execution.
        
        Raises:
            StartError: If start fails
            
        State Transition:
            INITIALIZED → STARTING → RUNNING
            
        Guarantees:
            - Event loop begins
            - Ready to receive events
            - Health checks start
            - Metrics collection begins
        """
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the component.
        
        Graceful shutdown. All in-flight work completes.
        Component will not accept new work.
        
        Raises:
            StopError: If stop fails
            
        State Transition:
            RUNNING → STOPPING → STOPPED
            
        Guarantees:
            - No new work accepted
            - In-flight work completes or is logged
            - Event subscriptions remain active (for recovery)
            - State persisted to durable storage
        """
        pass
    
    @abstractmethod
    async def health(self) -> HealthStatus:
        """
        Check component health.
        
        Non-blocking health check. Called periodically.
        
        Returns:
            HealthStatus: HEALTHY, DEGRADED, UNHEALTHY, UNKNOWN
            
        Response Time Requirement:
            - Must respond within 100ms
            - Must not block component execution
            
        Guarantees:
            - Does not modify state
            - Does not perform work
            - Checks internal invariants
        """
        pass
    
    @abstractmethod
    async def metrics(self) -> ComponentMetrics:
        """
        Return component metrics.
        
        Called by metrics engine.
        Returns standard metrics (uptime, errors, restarts, etc.)
        plus component-specific custom metrics.
        
        Returns:
            ComponentMetrics: Standard + custom metrics
            
        Guarantees:
            - Does not modify state
            - Does not perform work
            - Metrics are accurate as of invocation
        """
        pass
    
    @abstractmethod
    async def recover(self, reason: str) -> None:
        """
        Recover from error state.
        
        Called by Recovery Manager when:
        - Component crashed and restarted
        - Component was unhealthy
        - Stale locks/queues need cleanup
        - State inconsistency detected
        
        Args:
            reason: Why recovery is being triggered
            
        Raises:
            RecoveryError: If recovery fails
            
        State Transition:
            ERROR → RECOVERING → RUNNING
            
        Guarantees:
            - Deterministic (replay from audit log)
            - Idempotent (safe to call multiple times)
            - No duplicated work
            - State consistency verified
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """
        Shutdown component (teardown).
        
        Final cleanup before process exit.
        Release all resources (connections, locks, files).
        
        Raises:
            ShutdownError: If shutdown fails (warning only)
            
        State Transition:
            STOPPED → SHUTDOWN
            
        Guarantees:
            - All resources released
            - All locks released (force if needed)
            - All connections closed
            - Audit log flushed
            - Safe to exit process immediately after
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Component identifier (e.g., 'workflow-engine')."""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """Component version (e.g., '1.0.0')."""
        pass
    
    @property
    @abstractmethod
    def state(self) -> ComponentState:
        """Current component state."""
        pass
    
    @property
    @abstractmethod
    def dependencies(self) -> List[str]:
        """
        List of component names this component depends on.
        
        Dependencies are checked during initialization.
        If a required component is not available, initialization fails.
        
        Returns:
            List of required component names
            
        Important:
            These are RUNTIME dependencies (must be running).
            NOT code dependencies (no imports of other components).
        """
        pass
    
    @property
    @abstractmethod
    def provides(self) -> List[str]:
        """
        List of services/interfaces this component provides.
        
        Other components will subscribe to events from this component.
        
        Returns:
            List of service names
        """
        pass
```

---

## COMMUNICATION PATTERNS

### Pattern 1: Event-Driven (Preferred)

**Sender does NOT know receiver.**

```python
# Component A emits event
await event_bus.emit(Event(
    type="WORKFLOW_TRANSITIONED",
    capability_id="OBS-003",
    from_phase="IMPLEMENTATION",
    to_phase="QA"
))

# Component B (unknown to A) subscribes
event_bus.subscribe("WORKFLOW_TRANSITIONED", self.on_transition)

# Component B's handler
async def on_transition(event):
    # Component B reacts to event
    # Component A doesn't know about this handler
    pass
```

**Advantages**:
- ✅ Loose coupling (sender doesn't know receiver)
- ✅ Scalable (many receivers possible)
- ✅ Testable (emit events, verify side effects)
- ✅ Replaceable (swap receiver component)

---

### Pattern 2: Interface-Based (For Queries)

**Sender queries a service, doesn't care about implementation.**

```python
# Component A needs audit log access
audit_service = runtime.get_service("audit-engine")

# Component A calls interface method
entries = await audit_service.query(
    capability="OBS-003",
    event_type="GATE_EVALUATED"
)

# Component B (audit-engine) implements the interface
class AuditEngine(RuntimeComponent):
    async def query(self, **filters):
        # Implementation hidden from caller
        return self.backend.query(filters)
```

**Advantages**:
- ✅ Clean API (well-defined interface)
- ✅ Type-safe (interfaces define contracts)
- ✅ Testable (mock interfaces)
- ✅ Replaceable (different implementation, same interface)

---

### Pattern 3: Contract-Based (For Data)

**Components exchange data via contracts (data classes).**

```python
# Contract (shared between components)
class GateDecision(Contract):
    gate: str
    status: str  # PASS, FAIL, PENDING_EVIDENCE
    evidence_artifacts: List[str]
    timestamp: str

# Component A (Gate Evaluator) produces
decision = GateDecision(
    gate="QUALITY_ASSURANCE",
    status="PASS",
    evidence_artifacts=["artifact-123"],
    timestamp=datetime.utcnow().isoformat()
)

# Component B (Audit Engine) consumes
await audit_engine.record("GATE_DECISION", decision.to_dict())
```

**Advantages**:
- ✅ Explicit contracts (clear interface)
- ✅ Versioned (contracts have versions)
- ✅ Validated (type checking)
- ✅ Documented (contracts are documentation)

---

## COMPONENT STARTUP SEQUENCE

```
1. Initialize All Components
   ├─ Load configuration
   ├─ Validate dependencies (ensure required components available)
   ├─ Allocate resources
   └─ Internal state preparation
   
2. Start All Components (in dependency order)
   ├─ Start independent components first
   ├─ Start dependent components after dependencies are RUNNING
   ├─ Subscribe to required events
   └─ Enter RUNNING state
   
3. Verify All Components Healthy
   ├─ Call health() on each component
   ├─ Wait for all to respond HEALTHY
   ├─ If any unhealthy, escalate to Recovery Manager
   └─ Begin normal operation
```

---

## COMPONENT SHUTDOWN SEQUENCE

```
1. Stop All Components (in reverse dependency order)
   ├─ Stop dependent components first
   ├─ Allow in-flight work to complete
   ├─ Persist state to durable storage
   └─ Enter STOPPED state

2. Verify All Components Stopped
   ├─ Check all components are STOPPED
   └─ Wait for graceful shutdown (max 30 seconds)

3. Shutdown All Components
   ├─ Release all resources
   ├─ Close all connections
   ├─ Release all locks
   └─ Enter SHUTDOWN state
```

---

## RECOVERY SEQUENCE

```
Process crashes or component becomes unhealthy

↓

Recovery Manager detects (via health checks or process restart)

↓

Recovery Manager calls recover(reason="...")

↓

Component:
  ├─ Deterministically reconstruct state from audit log
  ├─ Verify no duplicated execution
  ├─ Verify all invariants maintained
  ├─ Resume from last consistent checkpoint
  └─ Return to RUNNING state
```

---

## EXAMPLE COMPONENT IMPLEMENTATION

### Minimal Component

```python
class WorkflowEngine(RuntimeComponent):
    """Example runtime component implementation."""
    
    def __init__(self):
        self._state = ComponentState.UNINITIALIZED
        self._config = None
        self._health_status = HealthStatus.UNKNOWN
        self._error_count = 0
        self._restart_count = 0
        self._initialized_at = None
        self._started_at = None
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize workflow engine."""
        if self._state != ComponentState.UNINITIALIZED:
            return  # Idempotent
        
        self._state = ComponentState.INITIALIZING
        
        try:
            self._config = config
            self._backend = PostgreSQL(config['database_url'])
            await self._backend.connect()
            self._initialized_at = datetime.utcnow()
            self._state = ComponentState.INITIALIZED
        except Exception as e:
            self._state = ComponentState.ERROR
            self._error_count += 1
            raise InitializationError(f"Failed to initialize: {e}")
    
    async def start(self) -> None:
        """Start workflow engine."""
        if self._state != ComponentState.INITIALIZED:
            raise StateError(f"Cannot start from state {self._state}")
        
        self._state = ComponentState.STARTING
        
        try:
            # Subscribe to events
            self.event_bus.subscribe("PHASE_TRANSITION", self.on_phase_transition)
            
            # Start background tasks
            asyncio.create_task(self._event_loop())
            
            self._started_at = datetime.utcnow()
            self._state = ComponentState.RUNNING
        except Exception as e:
            self._state = ComponentState.ERROR
            raise StartError(f"Failed to start: {e}")
    
    async def stop(self) -> None:
        """Stop workflow engine."""
        self._state = ComponentState.STOPPING
        
        try:
            # Stop accepting new work
            self._accepting_work = False
            
            # Wait for in-flight work (max 10 seconds)
            await asyncio.wait_for(
                self._wait_for_in_flight_work(),
                timeout=10.0
            )
            
            # Persist state
            await self._backend.persist_state(self.current_state)
            
            self._state = ComponentState.STOPPED
        except Exception as e:
            self._state = ComponentState.ERROR
            self._error_count += 1
    
    async def health(self) -> HealthStatus:
        """Check component health."""
        try:
            # Quick sanity checks
            if self._state != ComponentState.RUNNING:
                return HealthStatus.UNHEALTHY
            
            if self._error_count > 10:
                return HealthStatus.DEGRADED
            
            # Check backend connectivity
            if not await self._backend.ping():
                return HealthStatus.UNHEALTHY
            
            self._health_status = HealthStatus.HEALTHY
            return HealthStatus.HEALTHY
        except Exception:
            self._health_status = HealthStatus.UNHEALTHY
            return HealthStatus.UNHEALTHY
    
    async def metrics(self) -> ComponentMetrics:
        """Return component metrics."""
        return ComponentMetrics(
            initialized_at=self._initialized_at,
            started_at=self._started_at,
            stopped_at=None,
            error_count=self._error_count,
            restart_count=self._restart_count,
            uptime_seconds=self._calculate_uptime(),
            state=self._state,
            health=self._health_status,
            custom_metrics={
                "workflow_updates_processed": self._updates_processed,
                "state_transitions_completed": self._transitions_completed,
                "database_connection_active": await self._backend.ping()
            }
        )
    
    async def recover(self, reason: str) -> None:
        """Recover from error state."""
        logger.info(f"Recovering workflow engine: {reason}")
        
        self._state = ComponentState.RECOVERING
        
        try:
            # Restore from audit log
            last_checkpoint = await self._backend.get_last_checkpoint()
            self.current_state = last_checkpoint
            
            # Verify integrity
            if not await self._verify_state_integrity():
                raise RecoveryError("State integrity check failed")
            
            # Resume
            self._state = ComponentState.RUNNING
            self._restart_count += 1
        except Exception as e:
            self._state = ComponentState.ERROR
            raise RecoveryError(f"Recovery failed: {e}")
    
    async def shutdown(self) -> None:
        """Shutdown component."""
        try:
            if self._state != ComponentState.STOPPED:
                await self.stop()
            
            # Release all resources
            await self._backend.disconnect()
            
            self._state = ComponentState.SHUTDOWN
        except Exception as e:
            logger.warning(f"Error during shutdown: {e}")
    
    @property
    def name(self) -> str:
        return "workflow-engine"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def state(self) -> ComponentState:
        return self._state
    
    @property
    def dependencies(self) -> List[str]:
        return []  # Workflow Engine has no runtime dependencies
    
    @property
    def provides(self) -> List[str]:
        return ["workflow-service", "state-management"]
```

---

## DEPENDENCY INJECTION

### Service Locator Pattern

```python
class RuntimeServiceRegistry:
    """Service locator for runtime components."""
    
    def __init__(self):
        self._services = {}
    
    def register(self, name: str, component: RuntimeComponent):
        """Register component as service."""
        self._services[name] = component
    
    def get(self, name: str) -> RuntimeComponent:
        """Retrieve component by name."""
        if name not in self._services:
            raise ServiceNotFoundError(f"Service {name} not registered")
        return self._services[name]
    
    def get_all(self) -> Dict[str, RuntimeComponent]:
        """Get all registered components."""
        return self._services.copy()

# Usage
registry = RuntimeServiceRegistry()
registry.register("workflow-engine", workflow_engine)
registry.register("audit-engine", audit_engine)

# Component queries for services (not direct dependencies)
audit_engine = registry.get("audit-engine")
```

---

## TESTING GUIDELINES

### Unit Testing (Component Isolation)

```python
class TestWorkflowEngine(unittest.TestCase):
    """Test workflow engine in isolation."""
    
    async def test_initialize(self):
        """Test component initialization."""
        engine = WorkflowEngine()
        config = {"database_url": "sqlite:///:memory:"}
        
        await engine.initialize(config)
        
        self.assertEqual(engine.state, ComponentState.INITIALIZED)
    
    async def test_start(self):
        """Test component startup."""
        engine = WorkflowEngine()
        await engine.initialize(config)
        
        await engine.start()
        
        self.assertEqual(engine.state, ComponentState.RUNNING)
        health = await engine.health()
        self.assertEqual(health, HealthStatus.HEALTHY)
    
    async def test_health_check(self):
        """Test health check."""
        # No dependencies on other components
        # Can be tested standalone
        pass
    
    async def test_idempotent_initialize(self):
        """Test initialize is idempotent."""
        engine = WorkflowEngine()
        config = {"database_url": "sqlite:///:memory:"}
        
        await engine.initialize(config)
        await engine.initialize(config)  # Second call should be no-op
        
        self.assertEqual(engine.state, ComponentState.INITIALIZED)
```

### Integration Testing (Component Interaction)

```python
class TestRuntimeIntegration(unittest.TestCase):
    """Test components interacting via events."""
    
    async def test_workflow_transition_event(self):
        """Test workflow engine emits event that audit engine receives."""
        # Set up components
        workflow_engine = WorkflowEngine()
        audit_engine = AuditEngine()
        event_bus = EventBus()
        
        # Initialize and start
        await workflow_engine.initialize(config)
        await audit_engine.initialize(config)
        await event_bus.initialize()
        
        await workflow_engine.start()
        await audit_engine.start()
        
        # Workflow engine transitions phase
        await workflow_engine.transition_phase("SPECIFICATION", "DESIGN_REVIEW")
        
        # Audit engine should have recorded event
        entries = await audit_engine.query(event_type="PHASE_TRANSITION")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['from_phase'], "SPECIFICATION")
```

---

## DEPLOYMENT IMPLICATIONS

Each component can be deployed independently:

```bash
# Deploy only workflow-engine
$ helm install runtime-workflow-engine ./charts/drt-001

# Deploy only audit-engine
$ helm install runtime-audit-engine ./charts/drt-004

# No need to redeploy all components
# Components discover each other via event bus and service registry
```

---

## CERTIFICATION

**RuntimeComponent Interface**: ✅ **APPROVED**

This interface is the standard contract for all Dario Runtime components.

**Authority**: Chief Architect  
**Date**: 2026-07-13  
**Effective**: Immediately (for all DRT capabilities)

Every runtime component **MUST** implement this interface. Components that violate this interface will be rejected in code review.

---

**END OF SPECIFICATION**
