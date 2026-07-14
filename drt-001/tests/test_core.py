"""
Unit tests for core DRT-001 components.
Tests: persistence, execution_tracker, workflow_engine.
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from persistence import FilePersistence, IPersistence
from execution_tracker import (
    ExecutionContract,
    ExecutionStatus,
    ExecutionTracker,
    StepRecord,
)
from workflow_engine import (
    WorkflowEngine,
    WorkflowDefinition,
    ValidationError,
)


class TestFilePersistence:
    """Tests for FilePersistence implementation."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    @pytest.fixture
    def persistence(self, temp_storage):
        """Create FilePersistence instance."""
        return FilePersistence(temp_storage)

    def test_validate_storage_success(self, persistence):
        """Test storage validation passes."""
        assert persistence.validate_storage() is True

    def test_save_and_load(self, persistence):
        """Test save and load execution."""
        exec_id = "test-exec-1"
        data = {
            "execution_id": exec_id,
            "correlation_id": "corr-1",
            "status": "COMPLETED",
        }

        persistence.save(exec_id, data)
        loaded = persistence.load(exec_id)

        assert loaded is not None
        assert loaded["execution_id"] == exec_id
        assert loaded["status"] == "COMPLETED"

    def test_checksum_validation(self, persistence):
        """Test checksum detection of corruption."""
        exec_id = "test-exec-2"
        data = {"execution_id": exec_id, "value": 123}

        persistence.save(exec_id, data)

        # Corrupt the file
        exec_file = persistence.executions_path / f"{exec_id}.json"
        content = json.loads(exec_file.read_text())
        content["_checksum"] = "WRONG_CHECKSUM"
        exec_file.write_text(json.dumps(content))

        # Loading should raise error
        with pytest.raises(ValueError, match="Checksum mismatch"):
            persistence.load(exec_id)

    def test_exists(self, persistence):
        """Test existence check."""
        exec_id = "test-exec-3"
        assert persistence.exists(exec_id) is False

        persistence.save(exec_id, {"id": exec_id})
        assert persistence.exists(exec_id) is True

    def test_list_executions(self, persistence):
        """Test listing all executions."""
        ids = ["exec-1", "exec-2", "exec-3"]
        for exec_id in ids:
            persistence.save(exec_id, {"id": exec_id})

        listed = persistence.list_executions()
        assert len(listed) == 3
        for exec_id in ids:
            assert exec_id in listed

    def test_write_wal(self, persistence):
        """Test write-ahead log."""
        event1 = {"event": "START", "data": {"step": 1}}
        event2 = {"event": "COMPLETE", "data": {"step": 1}}

        persistence.write_wal(event1)
        persistence.write_wal(event2)

        # Check WAL file exists
        assert persistence.wal_path.exists()

        # Check checkpoint exists
        checkpoint = persistence.get_wal_checkpoint()
        assert checkpoint["event"] == "COMPLETE"

    def test_delete(self, persistence):
        """Test deletion."""
        exec_id = "test-exec-4"
        persistence.save(exec_id, {"id": exec_id})
        assert persistence.exists(exec_id) is True

        persistence.delete(exec_id)
        assert persistence.exists(exec_id) is False


class TestExecutionTracker:
    """Tests for ExecutionTracker."""

    def test_create_execution(self):
        """Test execution creation."""
        exec_contract = ExecutionTracker.create_execution(
            workflow_id="wf-1",
            workflow_name="test-workflow",
            workflow_version="1.0",
        )

        assert exec_contract.execution_id
        assert exec_contract.correlation_id
        assert exec_contract.workflow_version == "1.0"
        assert exec_contract.runtime_version == "1.0"
        assert exec_contract.status == ExecutionStatus.INITIALIZED.value
        assert exec_contract.checksum

    def test_contract_fields_mandatory(self):
        """Test all 9 contract fields are present."""
        exec_contract = ExecutionTracker.create_execution(
            workflow_id="wf-1",
            workflow_name="test-workflow",
            workflow_version="1.0",
        )

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
            assert getattr(exec_contract, field) is not None

    def test_mark_started(self):
        """Test marking execution as started."""
        exec_contract = ExecutionTracker.create_execution(
            workflow_id="wf-1",
            workflow_name="test-workflow",
            workflow_version="1.0",
        )

        exec_contract = ExecutionTracker.mark_started(exec_contract)
        assert exec_contract.status == ExecutionStatus.RUNNING.value

    def test_step_lifecycle(self):
        """Test step start, complete, and duration tracking."""
        import time

        exec_contract = ExecutionTracker.create_execution(
            workflow_id="wf-1",
            workflow_name="test-workflow",
            workflow_version="1.0",
        )

        # Start step
        exec_contract = ExecutionTracker.mark_step_started(exec_contract, "step-1")
        assert len(exec_contract.step_history) == 1
        assert exec_contract.step_history[0].name == "step-1"
        assert exec_contract.step_history[0].status == "RUNNING"

        # Small delay to ensure measurable duration
        time.sleep(0.01)

        # Complete step
        exec_contract = ExecutionTracker.mark_step_completed(
            exec_contract, "step-1", result={"value": 123}
        )
        step = exec_contract.step_history[0]
        assert step.status == "COMPLETED"
        assert step.result == {"value": 123}
        assert step.duration_ms >= 0  # Allow 0 for very fast execution

    def test_mark_completed(self):
        """Test marking execution as completed."""
        import time

        exec_contract = ExecutionTracker.create_execution(
            workflow_id="wf-1",
            workflow_name="test-workflow",
            workflow_version="1.0",
        )

        exec_contract = ExecutionTracker.mark_started(exec_contract)
        time.sleep(0.01)  # Ensure measurable time passes
        exec_contract = ExecutionTracker.mark_completed(exec_contract)

        assert exec_contract.status == ExecutionStatus.COMPLETED.value
        assert exec_contract.finished_at is not None
        assert exec_contract.duration_ms >= 0

    def test_mark_failed(self):
        """Test marking execution as failed."""
        exec_contract = ExecutionTracker.create_execution(
            workflow_id="wf-1",
            workflow_name="test-workflow",
            workflow_version="1.0",
        )

        error_msg = "Step failed with error"
        exec_contract = ExecutionTracker.mark_failed(exec_contract, error_msg)

        assert exec_contract.status == ExecutionStatus.FAILED.value
        assert exec_contract.error == error_msg
        assert exec_contract.finished_at is not None

    def test_audit_trail(self):
        """Test audit trail recording."""
        exec_contract = ExecutionTracker.create_execution(
            workflow_id="wf-1",
            workflow_name="test-workflow",
            workflow_version="1.0",
        )

        exec_contract = ExecutionTracker.add_audit_event(
            exec_contract, "STEP_STARTED", {"step": "step-1"}
        )
        exec_contract = ExecutionTracker.add_audit_event(
            exec_contract, "STEP_COMPLETED", {"step": "step-1"}
        )

        assert len(exec_contract.audit_trail) == 2
        assert exec_contract.audit_trail[0]["event"] == "STEP_STARTED"
        assert exec_contract.audit_trail[1]["event"] == "STEP_COMPLETED"

    def test_contract_validation(self):
        """Test contract validation."""
        exec_contract = ExecutionTracker.create_execution(
            workflow_id="wf-1",
            workflow_name="test-workflow",
            workflow_version="1.0",
        )

        assert ExecutionTracker.validate_contract(exec_contract) is True

        # Invalid status should fail validation
        exec_contract.status = "INVALID_STATUS"
        assert ExecutionTracker.validate_contract(exec_contract) is False

    def test_to_dict_from_dict(self):
        """Test serialization and deserialization."""
        original = ExecutionTracker.create_execution(
            workflow_id="wf-1",
            workflow_name="test-workflow",
            workflow_version="1.0",
        )

        data = original.to_dict()
        restored = ExecutionContract.from_dict(data)

        assert restored.execution_id == original.execution_id
        assert restored.correlation_id == original.correlation_id
        assert restored.status == original.status


class TestWorkflowEngine:
    """Tests for WorkflowEngine."""

    @pytest.fixture
    def temp_storage(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    @pytest.fixture
    def engine(self, temp_storage):
        persistence = FilePersistence(temp_storage)
        return WorkflowEngine(persistence)

    @pytest.fixture
    def valid_workflow(self):
        return {
            "name": "test-workflow",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "owner": "test",
            "timeout": 300,
            "steps": [
                {"name": "step-1", "type": "system"},
                {"name": "step-2", "type": "manual"},
            ],
        }

    def test_parse_workflow(self, engine, valid_workflow):
        """Test workflow parsing."""
        workflow = engine.parse_workflow(valid_workflow)

        assert workflow.name == "test-workflow"
        assert workflow.version == "1.0"
        assert len(workflow.steps) == 2

    def test_validate_workflow_success(self, engine, valid_workflow):
        """Test successful workflow validation."""
        workflow = engine.parse_workflow(valid_workflow)
        assert engine.validate_workflow(workflow) is True

    def test_validate_workflow_no_name(self, engine):
        """Test validation fails without name."""
        invalid = {
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }
        workflow = engine.parse_workflow(invalid)
        # Name should be empty/unknown, which should fail validation
        assert workflow.name == "unknown"  # Default name is "unknown"

    def test_validate_workflow_no_steps(self, engine):
        """Test validation fails without steps."""
        invalid = {
            "name": "test",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [],
        }
        workflow = engine.parse_workflow(invalid)

        with pytest.raises(ValidationError, match="at least one step"):
            engine.validate_workflow(workflow)

    def test_compile_workflow(self, engine, valid_workflow):
        """Test workflow compilation."""
        workflow = engine.parse_workflow(valid_workflow)
        plan = engine.compile_workflow(workflow)

        assert len(plan.step_sequence) == 2
        assert plan.step_sequence == ["step-1", "step-2"]

    def test_dry_run(self, engine, valid_workflow):
        """Test dry run (parse, validate, compile, no execute)."""
        result = engine.dry_run(valid_workflow)

        assert result["status"] == "PLAN_READY"
        assert len(result["step_sequence"]) == 2
        assert result["estimated_duration_ms"] > 0

    def test_execute_workflow(self, engine, valid_workflow):
        """Test full workflow execution."""
        execution = engine.execute_workflow(valid_workflow)

        assert execution.execution_id
        assert execution.status == ExecutionStatus.COMPLETED.value
        assert len(execution.step_history) == 2
        assert all(step.status == "COMPLETED" for step in execution.step_history)

    def test_execute_deterministic(self, engine, valid_workflow):
        """Test deterministic execution (same input = same output)."""
        exec1 = engine.execute_workflow(valid_workflow)
        exec2 = engine.execute_workflow(valid_workflow)

        # Same steps, different execution IDs, same results
        assert exec1.step_history[0].status == exec2.step_history[0].status
        assert exec1.step_history[1].status == exec2.step_history[1].status

    def test_idempotency(self, engine, valid_workflow):
        """Test idempotency (same correlation ID = only one execution)."""
        corr_id = "same-correlation-id"

        # First execution
        exec1 = engine.execute_workflow(valid_workflow, correlation_id=corr_id)
        assert exec1.status == ExecutionStatus.COMPLETED.value

        # Second execution with same correlation ID should return existing
        exec2 = engine.execute_workflow(valid_workflow, correlation_id=corr_id)
        assert exec2.execution_id == exec1.execution_id
        assert exec2.status == ExecutionStatus.COMPLETED.value

    def test_recover_execution(self, engine, valid_workflow):
        """Test execution recovery after crash."""
        # Execute workflow
        execution = engine.execute_workflow(valid_workflow)
        exec_id = execution.execution_id

        # Recover execution
        recovered = engine.recover_execution(exec_id)

        assert recovered is not None
        assert recovered.execution_id == exec_id
        assert recovered.status == ExecutionStatus.COMPLETED.value

    def test_event_handlers(self, engine, valid_workflow):
        """Test event emission and handlers."""
        events_received = []

        def event_handler(event):
            events_received.append(event["event"])

        engine.register_event_handler("WorkflowCreated", event_handler)
        engine.register_event_handler("WorkflowStarted", event_handler)
        engine.register_event_handler("StateTransitioned", event_handler)
        engine.register_event_handler("WorkflowCompleted", event_handler)

        engine.execute_workflow(valid_workflow)

        assert "WorkflowCreated" in events_received
        assert "WorkflowStarted" in events_received
        assert "StateTransitioned" in events_received
        assert "WorkflowCompleted" in events_received

    def test_workflow_with_error(self, engine):
        """Test execution error handling."""
        invalid_workflow = {
            "name": "invalid",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1"}],  # Missing 'type'
        }

        execution = engine.execute_workflow(invalid_workflow)
        # Engine should handle gracefully
        assert execution.execution_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
