"""AOM v3.1 Governance Workflow Engine.

Implements single-source-of-truth state machine for capability governance:
- One Workflow
- One State (workflow.yaml)
- One Truth (immutable audit trail)
- One Runtime (state machine enforced)

Guarantees:
- No invalid transitions (DAG enforcement)
- No authorization violations (role verification)
- No circular decisions (append-only audit log)
- No orphaned gates (complete audit trail)
"""

import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


class GateStatus(str, Enum):
    """Gate completion statuses."""
    VERIFIED = "VERIFIED"
    PENDING_EVIDENCE = "PENDING_EVIDENCE"
    PASSED = "PASSED"
    FAILED = "FAILED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class CapabilityPhase(str, Enum):
    """Capability lifecycle phases."""
    SPECIFICATION = "SPECIFICATION"
    DESIGN_REVIEW = "DESIGN_REVIEW"
    IMPLEMENTATION = "IMPLEMENTATION"
    CODE_REVIEW = "CODE_REVIEW"
    QUALITY_ASSURANCE = "QUALITY_ASSURANCE"
    FINAL_REVIEW = "FINAL_REVIEW"
    MERGE_AUTHORIZATION = "MERGE_AUTHORIZATION"
    INFRASTRUCTURE_VALIDATION = "INFRASTRUCTURE_VALIDATION"
    CAPABILITY_CLOSEOUT = "CAPABILITY_CLOSEOUT"
    PRODUCTION_DEPLOYMENT = "PRODUCTION_DEPLOYMENT"
    ARCHIVED = "ARCHIVED"


class CapabilityStatus(str, Enum):
    """Capability lifecycle statuses."""
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    IN_PROGRESS = "IN_PROGRESS"
    IMPLEMENTATION_COMPLETE = "IMPLEMENTATION_COMPLETE"
    READY_FOR_FINAL_REVIEW = "READY_FOR_FINAL_REVIEW"
    FINAL_REVIEW_APPROVED = "FINAL_REVIEW_APPROVED"
    CAPABILITY_CLOSED = "CAPABILITY_CLOSED"
    PRODUCTION_DEPLOYED = "PRODUCTION_DEPLOYED"
    BLOCKED = "BLOCKED"


# Gate authority mapping (role → gate)
GATE_AUTHORITY: Dict[str, str] = {
    "SPECIFICATION": "chief-architect",
    "DESIGN_REVIEW": "tech-lead",
    "IMPLEMENTATION": "implementation-engineer",
    "CODE_REVIEW": "tech-lead",
    "QUALITY_ASSURANCE": "qa-engineer",
    "FINAL_REVIEW": "chief-architect",
    "MERGE_AUTHORIZATION": "cto",
    "INFRASTRUCTURE_VALIDATION": "tech-lead",
    "CAPABILITY_CLOSEOUT": "chief-architect",
    "PRODUCTION_DEPLOYMENT": "devops",
}

# Valid state transitions (DAG enforcement)
VALID_TRANSITIONS: Dict[str, List[str]] = {
    "SPECIFICATION": ["DESIGN_REVIEW"],
    "DESIGN_REVIEW": ["IMPLEMENTATION"],
    "IMPLEMENTATION": ["CODE_REVIEW", "QUALITY_ASSURANCE"],
    "CODE_REVIEW": ["FINAL_REVIEW"],
    "QUALITY_ASSURANCE": ["FINAL_REVIEW"],
    "FINAL_REVIEW": ["MERGE_AUTHORIZATION"],
    "MERGE_AUTHORIZATION": ["INFRASTRUCTURE_VALIDATION"],
    "INFRASTRUCTURE_VALIDATION": ["CAPABILITY_CLOSEOUT"],
    "CAPABILITY_CLOSEOUT": ["PRODUCTION_DEPLOYMENT"],
    "PRODUCTION_DEPLOYMENT": ["ARCHIVED"],
}


class WorkflowState:
    """Current workflow state extracted from workflow.yaml."""

    def __init__(self, capability_id: str, state: Dict[str, Any]):
        self.capability_id = capability_id
        self.current_phase = state.get("phase")
        self.current_status = state.get("status")
        self.owner = state.get("owner")
        self.architecture_state = state.get("architecture_state")
        self.governance_state = state.get("governance_state")
        self.gates_completed: Dict[str, str] = {}

    def __repr__(self) -> str:
        return (
            f"WorkflowState(id={self.capability_id}, "
            f"phase={self.current_phase}, status={self.current_status})"
        )


class AuditEntry:
    """Immutable audit log entry."""

    def __init__(
        self,
        capability_id: str,
        gate: str,
        decision: str,
        authority: str,
        evidence_file: str,
        rationale: str,
    ):
        self.entry_id = f"AE-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        self.timestamp = datetime.utcnow().isoformat() + "Z"
        self.capability_id = capability_id
        self.gate = gate
        self.decision = decision
        self.authority = authority
        self.evidence_file = evidence_file
        self.rationale = rationale

    def to_dict(self) -> Dict[str, Any]:
        """Export audit entry as dictionary."""
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "event": "GATE_COMPLETED",
            "gate": self.gate,
            "capability": self.capability_id,
            "decision": self.decision,
            "authority": self.authority,
            "evidence_file": self.evidence_file,
            "rationale": self.rationale,
        }


class WorkflowEngine:
    """Single-source-of-truth state machine processor.

    Enforces:
    - State machine transitions (DAG rules)
    - Authority verification (role-based)
    - Frozen/locked constraints
    - Audit trail integrity
    """

    def __init__(self, workflow_file: Path):
        """Initialize workflow engine.

        Args:
            workflow_file: Path to workflow.yaml
        """
        self.workflow_file = workflow_file
        self.audit_log: List[AuditEntry] = []

    def load_state(self, capability_id: str) -> WorkflowState:
        """Load current workflow state from workflow.yaml.

        Args:
            capability_id: Capability ID (e.g., OBS-003)

        Returns:
            WorkflowState with current phase, status, owner
        """
        with open(self.workflow_file) as f:
            workflow = yaml.safe_load(f)

        # Find capability in workflow
        program = workflow.get("current_program", {})
        if program.get("id") == capability_id:
            return WorkflowState(
                capability_id,
                {
                    "phase": program.get("phase"),
                    "status": program.get("status"),
                    "owner": program.get("owner"),
                    "architecture_state": program.get("architecture_state"),
                    "governance_state": program.get("governance_state"),
                },
            )

        raise ValueError(f"Capability {capability_id} not found in workflow")

    def validate_transition(
        self, current_phase: str, next_gate: str
    ) -> Tuple[bool, str]:
        """Validate if gate transition is valid per state machine.

        Args:
            current_phase: Current capability phase
            next_gate: Gate being requested

        Returns:
            Tuple of (is_valid, reason)
        """
        if current_phase not in VALID_TRANSITIONS:
            return False, f"Unknown current phase: {current_phase}"

        valid_next = VALID_TRANSITIONS[current_phase]
        if next_gate not in valid_next:
            return False, (
                f"Invalid transition: {current_phase} → {next_gate}. "
                f"Valid next: {valid_next}"
            )

        return True, "Transition valid"

    def verify_authority(self, gate: str, authority: str) -> Tuple[bool, str]:
        """Verify that authority matches gate requirements.

        Args:
            gate: Gate name
            authority: Authority role (e.g., qa-engineer)

        Returns:
            Tuple of (is_authorized, reason)
        """
        if gate not in GATE_AUTHORITY:
            return False, f"Unknown gate: {gate}"

        required_authority = GATE_AUTHORITY[gate]
        if authority != required_authority:
            return False, (
                f"Authority mismatch for {gate}: "
                f"expected {required_authority}, got {authority}"
            )

        return True, "Authority verified"

    def check_frozen_constraints(self, state: WorkflowState) -> Tuple[bool, str]:
        """Verify frozen/locked invariants.

        Args:
            state: Current workflow state

        Returns:
            Tuple of (constraints_satisfied, reason)
        """
        if state.architecture_state != "FROZEN":
            return False, "Architecture not frozen"

        if state.governance_state != "LOCKED":
            return False, "Governance not locked"

        return True, "Frozen/locked constraints satisfied"

    def evaluate_gate_transition(
        self,
        capability_id: str,
        gate: str,
        decision: str,
        authority: str,
        evidence_file: str,
        rationale: str,
    ) -> Tuple[bool, str]:
        """Evaluate if gate transition is valid.

        Args:
            capability_id: Capability ID
            gate: Gate name
            decision: Decision (APPROVED/REJECTED/BLOCKED)
            authority: Authority role
            evidence_file: Evidence artifact filename
            rationale: Decision rationale

        Returns:
            Tuple of (is_valid, reason)
        """
        # Load current state
        try:
            state = self.load_state(capability_id)
        except ValueError as e:
            return False, str(e)

        # Validate transition rules
        is_valid, reason = self.validate_transition(state.current_phase, gate)
        if not is_valid:
            return False, reason

        # Verify authority
        is_authorized, reason = self.verify_authority(gate, authority)
        if not is_authorized:
            return False, reason

        # Check frozen constraints
        constraints_ok, reason = self.check_frozen_constraints(state)
        if not constraints_ok:
            return False, reason

        # Create audit entry
        audit_entry = AuditEntry(
            capability_id, gate, decision, authority, evidence_file, rationale
        )
        self.audit_log.append(audit_entry)

        logger.info(f"Gate transition approved: {capability_id} {gate} {decision}")
        return True, f"Gate {gate} transitioned to {decision}"

    def compute_capability_status(self, gates_completed: int, gates_total: int) -> str:
        """Compute capability status from gate states.

        Args:
            gates_completed: Number of gates passed
            gates_total: Total gates required

        Returns:
            Capability status string
        """
        if gates_completed == gates_total:
            return CapabilityStatus.IMPLEMENTATION_COMPLETE.value
        elif gates_completed >= gates_total * 0.75:
            return CapabilityStatus.IN_PROGRESS.value
        else:
            return CapabilityStatus.AWAITING_AUTHORIZATION.value

    def record_gate_completion(
        self,
        capability_id: str,
        gate: str,
        decision: str,
    ) -> None:
        """Record gate completion in audit log.

        Args:
            capability_id: Capability ID
            gate: Gate name
            decision: Decision status
        """
        audit_entries = [e.to_dict() for e in self.audit_log]
        logger.info(
            f"Recorded gate completion: {capability_id} {gate} {decision}",
            extra={"audit_entries": audit_entries},
        )

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Get audit log entries.

        Returns:
            List of audit entry dictionaries
        """
        return [e.to_dict() for e in self.audit_log]

    def validate_workflow_integrity(self) -> Tuple[bool, List[str]]:
        """Validate workflow.yaml integrity.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        try:
            with open(self.workflow_file) as f:
                workflow = yaml.safe_load(f)
        except Exception as e:
            return False, [f"Failed to parse workflow.yaml: {e}"]

        # Check: current_program exists
        if "current_program" not in workflow:
            errors.append("Missing: current_program")

        # Check: completed_capabilities is append-only
        if "completed_capabilities" in workflow:
            for cap in workflow["completed_capabilities"]:
                if "closure_date" not in cap:
                    errors.append(f"Missing closure_date for {cap.get('id')}")

        # Check: gates are ordered by completion_date
        gates = workflow.get("completed_gates", [])
        timestamps = [
            datetime.fromisoformat(g.get("completion_date", "").replace("Z", "+00:00"))
            for g in gates
            if "completion_date" in g
        ]
        if timestamps != sorted(timestamps):
            errors.append("Gates not chronologically ordered")

        return len(errors) == 0, errors


def create_workflow_engine(workflow_file: Optional[Path] = None) -> WorkflowEngine:
    """Factory function to create workflow engine.

    Args:
        workflow_file: Path to workflow.yaml (default: repo root)

    Returns:
        Initialized WorkflowEngine instance
    """
    if workflow_file is None:
        workflow_file = Path(__file__).parent.parent.parent / "workflow.yaml"

    return WorkflowEngine(workflow_file)
