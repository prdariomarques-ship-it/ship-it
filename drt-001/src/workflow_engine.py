"""
Core workflow engine.
Parse, validate, compile, and execute workflows deterministically.
"""

import json
import time
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

from execution_tracker import ExecutionContract, ExecutionStatus, ExecutionTracker
from persistence import IPersistence


class ValidationError(Exception):
    """Workflow validation error."""
    pass


class WorkflowStep:
    """Parsed workflow step."""

    def __init__(self, name: str, step_type: str, config: Dict[str, Any]):
        self.name = name
        self.type = step_type
        self.config = config

    def validate(self) -> bool:
        """Validate step configuration."""
        if not self.name or not self.type:
            return False
        return True


class WorkflowDefinition:
    """Parsed workflow definition."""

    def __init__(self, yaml_data: Dict[str, Any]):
        self.name = yaml_data.get("name", "unknown")
        self.version = yaml_data.get("workflow_version", "1.0")
        self.runtime_version = yaml_data.get("runtime_version", "1.0")
        self.owner = yaml_data.get("owner", "unknown")
        self.timeout = yaml_data.get("timeout", 300)
        self.retry_policy = yaml_data.get("retry_policy", "none")
        self.created_at = yaml_data.get("created_at", datetime.utcnow().isoformat() + "Z")
        self.description = yaml_data.get("description", "")

        # Parse steps
        self.steps: List[WorkflowStep] = []
        for step_data in yaml_data.get("steps", []):
            if isinstance(step_data, dict):
                step = WorkflowStep(
                    name=step_data.get("name"),
                    step_type=step_data.get("type", "system"),
                    config=step_data,
                )
                self.steps.append(step)

    def validate(self) -> bool:
        """Validate workflow definition."""
        if not self.name:
            raise ValidationError("Workflow must have a name")

        if not self.version:
            raise ValidationError("Workflow must have workflow_version")

        if not self.runtime_version:
            raise ValidationError("Workflow must have runtime_version")

        if not self.steps:
            raise ValidationError("Workflow must have at least one step")

        # Validate timeout is positive
        if self.timeout <= 0:
            raise ValidationError("Workflow timeout must be positive")

        # Check for duplicate step names
        step_names = {s.name for s in self.steps}
        if len(step_names) != len(self.steps):
            raise ValidationError("Duplicate step names not allowed")

        for step in self.steps:
            if not step.validate():
                raise ValidationError(f"Invalid step: {step.name}")

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "workflow_version": self.version,
            "runtime_version": self.runtime_version,
            "owner": self.owner,
            "timeout": self.timeout,
            "retry_policy": self.retry_policy,
            "created_at": self.created_at,
            "description": self.description,
            "steps": [
                {
                    "name": s.name,
                    "type": s.type,
                    "config": s.config,
                }
                for s in self.steps
            ],
        }


class ExecutionPlan:
    """Compiled execution plan (ready to run)."""

    def __init__(self, workflow: WorkflowDefinition):
        self.workflow = workflow
        self.step_sequence = [step.name for step in workflow.steps]
        self.step_configs = {step.name: step.config for step in workflow.steps}
        self.estimated_duration_ms = workflow.timeout * 1000

    def validate(self) -> bool:
        """Validate execution plan is valid."""
        if not self.step_sequence:
            return False
        return True


class WorkflowEngine:
    """Core workflow execution engine."""

    def __init__(self, persistence: IPersistence):
        self.persistence = persistence
        self.event_handlers: Dict[str, List[Callable]] = {
            "WorkflowCreated": [],
            "WorkflowStarted": [],
            "StateTransitioned": [],
            "WorkflowCompleted": [],
            "WorkflowFailed": [],
            "WorkflowRecovered": [],
        }
        # Index correlation_id -> execution_id for O(1) idempotency lookup
        self.correlation_index: Dict[str, str] = {}
        self._build_correlation_index()

    def _build_correlation_index(self) -> None:
        """Build index of correlation_id -> execution_id on startup for O(1) lookup."""
        for exec_id in self.persistence.list_executions():
            try:
                data = self.persistence.load(exec_id)
                correlation_id = data.get("correlation_id")
                if correlation_id:
                    self.correlation_index[correlation_id] = exec_id
            except Exception:
                continue

    def register_event_handler(
        self, event_name: str, handler: Callable[[Dict[str, Any]], None]
    ) -> None:
        """Register an event handler."""
        if event_name in self.event_handlers:
            self.event_handlers[event_name].append(handler)

    def _emit_event(self, event_name: str, data: Dict[str, Any]) -> None:
        """Emit internal event and invoke handlers."""
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": event_name,
            "data": data,
        }

        # Persist to WAL
        self.persistence.write_wal(event)

        # Invoke local handlers
        for handler in self.event_handlers.get(event_name, []):
            try:
                handler(event)
            except Exception:
                pass

    def parse_workflow(self, yaml_data: Dict[str, Any]) -> WorkflowDefinition:
        """Parse YAML into workflow definition."""
        if not isinstance(yaml_data, dict):
            raise ValidationError("Workflow must be a dictionary")

        return WorkflowDefinition(yaml_data)

    def validate_workflow(self, workflow: WorkflowDefinition) -> bool:
        """Validate workflow definition."""
        return workflow.validate()

    def compile_workflow(self, workflow: WorkflowDefinition) -> ExecutionPlan:
        """Compile workflow into execution plan."""
        if not self.validate_workflow(workflow):
            raise ValidationError("Workflow validation failed")

        plan = ExecutionPlan(workflow)
        if not plan.validate():
            raise ValidationError("Execution plan validation failed")

        return plan

    def dry_run(self, yaml_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dry run: Parse → Validate → Compile → Plan (no execution).
        Returns execution plan without executing.
        """
        workflow = self.parse_workflow(yaml_data)
        self.validate_workflow(workflow)
        plan = self.compile_workflow(workflow)

        return {
            "workflow": workflow.to_dict(),
            "step_sequence": plan.step_sequence,
            "estimated_duration_ms": plan.estimated_duration_ms,
            "status": "PLAN_READY",
        }

    def check_idempotency(self, correlation_id: str) -> Optional[ExecutionContract]:
        """
        Check if execution with this correlation_id already exists (O(1) lookup).
        If found, return it (resume from last completed step).
        """
        # O(1) lookup via index
        exec_id = self.correlation_index.get(correlation_id)
        if not exec_id:
            return None

        try:
            data = self.persistence.load(exec_id)
            return ExecutionContract.from_dict(data)
        except Exception:
            return None

    def execute_workflow(
        self,
        yaml_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> ExecutionContract:
        """
        Execute workflow end-to-end.
        1. Parse
        2. Validate
        3. Compile
        4. Check idempotency
        5. Execute steps
        6. Persist results
        7. Return execution record
        """
        # Step 1: Parse
        workflow = self.parse_workflow(yaml_data)

        # Step 2: Validate
        self.validate_workflow(workflow)

        # Step 3: Compile
        plan = self.compile_workflow(workflow)

        # Step 4: Check idempotency
        existing = self.check_idempotency(correlation_id) if correlation_id else None
        if existing and existing.status == ExecutionStatus.COMPLETED.value:
            # Already completed - resume and return
            self._emit_event(
                "WorkflowRecovered",
                {
                    "execution_id": existing.execution_id,
                    "correlation_id": correlation_id,
                    "status": existing.status,
                },
            )
            return existing

        # Step 5: Create execution record
        execution = ExecutionTracker.create_execution(
            workflow_id=workflow.name,
            workflow_name=workflow.name,
            workflow_version=workflow.version,
            correlation_id=correlation_id,
        )

        # Add to correlation index for future lookups
        if correlation_id:
            self.correlation_index[correlation_id] = execution.execution_id

        self._emit_event(
            "WorkflowCreated",
            {
                "execution_id": execution.execution_id,
                "workflow_name": workflow.name,
            },
        )

        # Mark as started
        execution = ExecutionTracker.mark_started(execution)
        self._emit_event(
            "WorkflowStarted",
            {
                "execution_id": execution.execution_id,
                "step_count": len(plan.step_sequence),
            },
        )

        # Step 6: Execute steps with timeout enforcement
        start_time = time.time()
        timeout_seconds = plan.workflow.timeout
        try:
            for step_name in plan.step_sequence:
                # Check if timeout exceeded
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    raise TimeoutError(
                        f"Workflow timeout exceeded ({elapsed:.1f}s > {timeout_seconds}s)"
                    )

                # Mark step started
                execution = ExecutionTracker.mark_step_started(execution, step_name)

                self._emit_event(
                    "StateTransitioned",
                    {
                        "execution_id": execution.execution_id,
                        "step": step_name,
                        "status": "STARTED",
                    },
                )

                # Simulate step execution (deterministic)
                result = self._execute_step(step_name, plan.step_configs[step_name])

                # Mark step completed
                execution = ExecutionTracker.mark_step_completed(
                    execution, step_name, result
                )

                self._emit_event(
                    "StateTransitioned",
                    {
                        "execution_id": execution.execution_id,
                        "step": step_name,
                        "status": "COMPLETED",
                        "result": result,
                    },
                )

                # Persist after each step (durability)
                self.persistence.save(execution.execution_id, execution.to_dict())

            # Step 7: Mark completed
            execution = ExecutionTracker.mark_completed(execution)
            self._emit_event(
                "WorkflowCompleted",
                {
                    "execution_id": execution.execution_id,
                    "duration_ms": execution.duration_ms,
                },
            )

        except Exception as e:
            execution = ExecutionTracker.mark_failed(execution, str(e))
            self._emit_event(
                "WorkflowFailed",
                {
                    "execution_id": execution.execution_id,
                    "error": str(e),
                },
            )

        # Final persistence
        self.persistence.save(execution.execution_id, execution.to_dict())

        # Add audit entry
        execution = ExecutionTracker.add_audit_event(
            execution,
            "WORKFLOW_COMPLETED" if execution.status == ExecutionStatus.COMPLETED.value else "WORKFLOW_FAILED",
            {"duration_ms": execution.duration_ms},
        )

        # Final persistence with audit
        self.persistence.save(execution.execution_id, execution.to_dict())

        return execution

    def _execute_step(self, step_name: str, config: Dict[str, Any]) -> Any:
        """Execute a single step (deterministic, no side effects)."""
        step_type = config.get("type", "system")

        if step_type == "manual":
            return {"status": "approved", "step": step_name}
        elif step_type == "system":
            return {"status": "completed", "step": step_name}
        else:
            return {"status": "unknown", "step": step_name}

    def recover_execution(self, execution_id: str) -> Optional[ExecutionContract]:
        """
        Recover execution after crash.
        1. Check if execution exists
        2. Load from persistence
        3. Verify checksum
        4. If incomplete, mark recovered
        """
        try:
            data = self.persistence.load(execution_id)
            if not data:
                return None

            execution = ExecutionContract.from_dict(data)

            # Verify checksum
            original_checksum = execution.checksum
            execution.checksum = ""
            computed_checksum = ExecutionTracker._generate_checksum(execution)
            execution.checksum = original_checksum

            if computed_checksum != original_checksum:
                raise ValueError("Checksum mismatch - data corrupted")

            # Mark recovered if incomplete
            if execution.status != ExecutionStatus.COMPLETED.value:
                execution = ExecutionTracker.mark_recovered(execution)
                self.persistence.save(execution_id, execution.to_dict())

                self._emit_event(
                    "WorkflowRecovered",
                    {
                        "execution_id": execution_id,
                        "status": execution.status,
                    },
                )

            return execution
        except Exception:
            return None
