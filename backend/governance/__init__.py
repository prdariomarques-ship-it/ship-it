"""AOM v3.1 Governance framework for capability lifecycle management.

Provides:
- Workflow engine (single source of truth state machine)
- Gate management (authority verification, transition rules)
- Audit logging (immutable governance record)
- Evidence collection (objective verification pipeline)
- Quality scoring (AOM-QA-001 compliance)
"""

from backend.governance.workflow_engine import (
    WorkflowEngine,
    WorkflowState,
    AuditEntry,
    GateStatus,
    CapabilityPhase,
    CapabilityStatus,
    create_workflow_engine,
)

__all__ = [
    "WorkflowEngine",
    "WorkflowState",
    "AuditEntry",
    "GateStatus",
    "CapabilityPhase",
    "CapabilityStatus",
    "create_workflow_engine",
]
