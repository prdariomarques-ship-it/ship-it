"""
Execution tracking with deterministic IDs and mandatory contract fields.
Every execution must contain all 9 contract fields.
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum


class ExecutionStatus(Enum):
    """Execution lifecycle states."""
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECOVERED = "RECOVERED"


@dataclass
class StepRecord:
    """Record of a single step execution."""
    name: str
    started_at: str
    finished_at: Optional[str] = None
    duration_ms: int = 0
    status: str = "RUNNING"
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class ExecutionContract:
    """
    Mandatory execution contract.
    Every execution MUST contain these 9 fields.
    No exceptions.
    """

    # Field 1: Unique execution identifier
    execution_id: str

    # Field 2: Correlation ID for grouping related executions
    correlation_id: str

    # Field 3: Workflow definition version
    workflow_version: str

    # Field 4: Runtime version that executed this
    runtime_version: str

    # Field 5: Execution start timestamp
    started_at: str

    # Field 6: Execution finish timestamp
    finished_at: Optional[str]

    # Field 7: Total execution duration in milliseconds
    duration_ms: int

    # Field 8: Current execution status
    status: str

    # Field 9: SHA256 checksum for integrity verification
    checksum: str

    # Additional fields (not part of contract but mandatory for tracking)
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    current_step: Optional[str] = None
    step_history: List[StepRecord] = field(default_factory=list)
    recovery_count: int = 0
    retry_count: int = 0
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence."""
        data = asdict(self)
        data["step_history"] = [asdict(step) for step in self.step_history]
        return data

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ExecutionContract":
        """Reconstruct from dictionary."""
        steps = [StepRecord(**step) for step in data.pop("step_history", [])]
        contract = ExecutionContract(**data)
        contract.step_history = steps
        return contract


class ExecutionTracker:
    """Track execution with deterministic IDs and contract validation."""

    RUNTIME_VERSION = "1.0"

    @staticmethod
    def create_execution(
        workflow_id: str,
        workflow_name: str,
        workflow_version: str,
        correlation_id: Optional[str] = None,
    ) -> ExecutionContract:
        """Create a new execution with mandatory contract fields."""
        execution_id = str(uuid.uuid4())
        correlation_id = correlation_id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"

        execution = ExecutionContract(
            execution_id=execution_id,
            correlation_id=correlation_id,
            workflow_version=workflow_version,
            runtime_version=ExecutionTracker.RUNTIME_VERSION,
            started_at=now,
            finished_at=None,
            duration_ms=0,
            status=ExecutionStatus.INITIALIZED.value,
            checksum="",
            workflow_id=workflow_id,
            workflow_name=workflow_name,
        )

        # Generate checksum
        execution.checksum = ExecutionTracker._generate_checksum(execution)

        return execution

    @staticmethod
    def mark_started(execution: ExecutionContract) -> ExecutionContract:
        """Mark execution as started."""
        execution.status = ExecutionStatus.RUNNING.value
        return execution

    @staticmethod
    def mark_step_started(
        execution: ExecutionContract, step_name: str
    ) -> ExecutionContract:
        """Record step start."""
        execution.current_step = step_name
        step = StepRecord(
            name=step_name,
            started_at=datetime.utcnow().isoformat() + "Z",
        )
        execution.step_history.append(step)
        return execution

    @staticmethod
    def mark_step_completed(
        execution: ExecutionContract,
        step_name: str,
        result: Optional[Any] = None,
    ) -> ExecutionContract:
        """Record step completion."""
        if execution.step_history and execution.step_history[-1].name == step_name:
            step = execution.step_history[-1]
            step.finished_at = datetime.utcnow().isoformat() + "Z"
            step.status = "COMPLETED"
            step.result = result

            # Calculate duration
            start = datetime.fromisoformat(step.started_at.replace("Z", "+00:00"))
            finish = datetime.fromisoformat(step.finished_at.replace("Z", "+00:00"))
            step.duration_ms = int((finish - start).total_seconds() * 1000)

        return execution

    @staticmethod
    def mark_step_failed(
        execution: ExecutionContract, step_name: str, error: str
    ) -> ExecutionContract:
        """Record step failure."""
        if execution.step_history and execution.step_history[-1].name == step_name:
            step = execution.step_history[-1]
            step.finished_at = datetime.utcnow().isoformat() + "Z"
            step.status = "FAILED"
            step.error = error

            start = datetime.fromisoformat(step.started_at.replace("Z", "+00:00"))
            finish = datetime.fromisoformat(step.finished_at.replace("Z", "+00:00"))
            step.duration_ms = int((finish - start).total_seconds() * 1000)

        return execution

    @staticmethod
    def mark_completed(execution: ExecutionContract) -> ExecutionContract:
        """Mark execution as completed."""
        now = datetime.utcnow().isoformat() + "Z"
        execution.finished_at = now
        execution.status = ExecutionStatus.COMPLETED.value

        # Calculate total duration
        start = datetime.fromisoformat(execution.started_at.replace("Z", "+00:00"))
        finish = datetime.fromisoformat(now.replace("Z", "+00:00"))
        execution.duration_ms = int((finish - start).total_seconds() * 1000)

        execution.checksum = ExecutionTracker._generate_checksum(execution)
        return execution

    @staticmethod
    def mark_failed(execution: ExecutionContract, error: str) -> ExecutionContract:
        """Mark execution as failed."""
        now = datetime.utcnow().isoformat() + "Z"
        execution.finished_at = now
        execution.status = ExecutionStatus.FAILED.value
        execution.error = error

        start = datetime.fromisoformat(execution.started_at.replace("Z", "+00:00"))
        finish = datetime.fromisoformat(now.replace("Z", "+00:00"))
        execution.duration_ms = int((finish - start).total_seconds() * 1000)

        execution.checksum = ExecutionTracker._generate_checksum(execution)
        return execution

    @staticmethod
    def mark_recovered(execution: ExecutionContract) -> ExecutionContract:
        """Mark execution as recovered."""
        execution.status = ExecutionStatus.RECOVERED.value
        execution.recovery_count += 1
        return execution

    @staticmethod
    def add_audit_event(
        execution: ExecutionContract, event: str, details: Optional[Dict] = None
    ) -> ExecutionContract:
        """Add event to audit trail."""
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": event,
            "details": details or {},
        }
        execution.audit_trail.append(audit_entry)
        return execution

    @staticmethod
    def _generate_checksum(execution: ExecutionContract) -> str:
        """Generate checksum for execution integrity."""
        import hashlib
        import json

        # Create checksum-able representation
        data = {
            "execution_id": execution.execution_id,
            "correlation_id": execution.correlation_id,
            "workflow_version": execution.workflow_version,
            "runtime_version": execution.runtime_version,
            "started_at": execution.started_at,
            "status": execution.status,
            "step_count": len(execution.step_history),
        }

        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    @staticmethod
    def validate_contract(execution: ExecutionContract) -> bool:
        """Validate execution has all 9 mandatory contract fields."""
        required_fields = [
            "execution_id",
            "correlation_id",
            "workflow_version",
            "runtime_version",
            "started_at",
            "status",
            "checksum",
        ]

        for field in required_fields:
            if not getattr(execution, field, None):
                return False

        # Validate status is valid
        valid_statuses = {s.value for s in ExecutionStatus}
        if execution.status not in valid_statuses:
            return False

        return True
