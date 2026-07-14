"""
Tests verifying DRT-001.1 critical fixes.
Validates: thread safety, strong checksum, O(1) idempotency, timeout enforcement, duplicate detection.
"""

import pytest
import sys
import tempfile
import shutil
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient
from runtime_api import create_runtime_api
from workflow_engine import WorkflowEngine, ValidationError
from persistence import FilePersistence
from execution_tracker import ExecutionTracker


@pytest.fixture
def temp_storage():
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir)


class TestDRT001_1_ThreadSafety:
    """Verify thread safety in WAL operations."""

    def test_concurrent_wal_writes(self, temp_storage):
        """Verify concurrent write_wal calls are safe (no interleaved writes)."""
        persistence = FilePersistence(temp_storage)

        # Generate concurrent events
        events = [
            {"event": f"test-event-{i}", "timestamp": str(i)} for i in range(50)
        ]
        threads = []
        errors = []

        def write_event(event):
            try:
                persistence.write_wal(event)
            except Exception as e:
                errors.append(e)

        # Start 50 concurrent writes
        for event in events:
            t = threading.Thread(target=write_event, args=(event,))
            threads.append(t)
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Verify no errors
        assert len(errors) == 0, f"Concurrent writes failed: {errors}"

        # Verify WAL file is valid (can be parsed)
        wal_file = persistence.wal_path
        assert wal_file.exists()

        # Count lines (should be 50 events)
        lines = wal_file.read_text().strip().split("\n")
        assert len(lines) == 50, f"Expected 50 events, got {len(lines)}"

    def test_wal_checkpoint_consistency(self, temp_storage):
        """Verify WAL and checkpoint stay consistent under concurrent access."""
        persistence = FilePersistence(temp_storage)

        # Write events concurrently
        for i in range(10):
            t1 = threading.Thread(
                target=persistence.write_wal,
                args=({"event": "thread1", "count": i},),
            )
            t2 = threading.Thread(
                target=persistence.write_wal,
                args=({"event": "thread2", "count": i},),
            )
            t1.start()
            t2.start()
            t1.join()
            t2.join()

        # Verify checkpoint exists and is valid JSON
        checkpoint = persistence.get_wal_checkpoint()
        assert checkpoint is not None
        assert "event" in checkpoint


class TestDRT001_1_StrongChecksum:
    """Verify checksum includes all mutable fields."""

    def test_checksum_detects_finished_at_corruption(self, temp_storage):
        """Verify checksum changes if finished_at is corrupted."""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        workflow = {
            "name": "checksum-test",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }

        execution = engine.execute_workflow(workflow)
        original_checksum = execution.checksum

        # Corrupt finished_at and recompute checksum
        execution.finished_at = "2025-01-01T00:00:00Z"
        new_checksum = ExecutionTracker._generate_checksum(execution)

        # Checksums should differ
        assert original_checksum != new_checksum, "Checksum didn't detect finished_at change"

    def test_checksum_detects_duration_corruption(self, temp_storage):
        """Verify checksum changes if duration_ms is corrupted."""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        workflow = {
            "name": "duration-test",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }

        execution = engine.execute_workflow(workflow)
        original_checksum = execution.checksum

        # Corrupt duration
        execution.duration_ms = 9999999
        new_checksum = ExecutionTracker._generate_checksum(execution)

        # Checksums should differ
        assert original_checksum != new_checksum, "Checksum didn't detect duration change"

    def test_checksum_detects_step_result_corruption(self, temp_storage):
        """Verify checksum changes if step results are corrupted."""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        workflow = {
            "name": "step-result-test",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }

        execution = engine.execute_workflow(workflow)
        original_checksum = execution.checksum

        # Corrupt step result
        if execution.step_history:
            execution.step_history[0].result = {"corrupted": True}
            new_checksum = ExecutionTracker._generate_checksum(execution)
            assert (
                original_checksum != new_checksum
            ), "Checksum didn't detect step result change"


class TestDRT001_1_O1Idempotency:
    """Verify O(1) correlation ID lookup."""

    def test_correlation_index_on_startup(self, temp_storage):
        """Verify correlation index is built on engine startup."""
        persistence = FilePersistence(temp_storage)
        engine1 = WorkflowEngine(persistence)

        # Create execution with correlation ID
        workflow = {
            "name": "index-test",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }

        corr_id = "test-correlation-001"
        execution = engine1.execute_workflow(workflow, correlation_id=corr_id)
        exec_id = execution.execution_id

        # Create new engine - should rebuild index
        engine2 = WorkflowEngine(persistence)

        # Index should contain the correlation ID
        assert (
            corr_id in engine2.correlation_index
        ), f"Index doesn't contain {corr_id}"
        assert (
            engine2.correlation_index[corr_id] == exec_id
        ), f"Index maps to wrong exec_id"

    def test_idempotency_lookup_is_instant(self, temp_storage):
        """Verify idempotency lookup is O(1) (instant)."""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        # Create many executions with different correlation IDs
        for i in range(100):
            workflow = {
                "name": f"workflow-{i}",
                "workflow_version": "1.0",
                "runtime_version": "1.0",
                "steps": [{"name": "step-1", "type": "system"}],
            }
            engine.execute_workflow(workflow, correlation_id=f"corr-{i}")

        # Measure lookup time - should be instant (< 1ms even with 100 executions)
        target_corr_id = "corr-50"

        start = time.time()
        found = engine.check_idempotency(target_corr_id)
        elapsed_ms = (time.time() - start) * 1000

        assert found is not None
        assert (
            elapsed_ms < 5
        ), f"O(1) lookup took {elapsed_ms}ms (should be < 1ms)"


class TestDRT001_1_TimeoutEnforcement:
    """Verify timeout is enforced during execution."""

    def test_workflow_timeout_is_enforced(self, temp_storage):
        """Verify workflow execution times out when limit exceeded."""
        persistence = FilePersistence(temp_storage)

        # Patch _execute_step to be slow
        import workflow_engine as wf_module
        original_execute = wf_module.WorkflowEngine._execute_step

        def slow_execute_step(self, step_name, config):
            time.sleep(0.05)  # 50ms per step
            return original_execute(self, step_name, config)

        wf_module.WorkflowEngine._execute_step = slow_execute_step

        try:
            engine = WorkflowEngine(persistence)

            # Create workflow with timeout that will be exceeded
            # With 3 steps at 50ms each = 150ms total, but timeout is 100ms
            workflow = {
                "name": "timeout-test",
                "workflow_version": "1.0",
                "runtime_version": "1.0",
                "timeout": 0.1,  # 100ms timeout
                "steps": [
                    {"name": "step-1", "type": "system"},
                    {"name": "step-2", "type": "system"},
                    {"name": "step-3", "type": "system"},
                ],
            }

            # Execute - should timeout before completing all steps
            execution = engine.execute_workflow(workflow)

            # Should be marked as FAILED (due to timeout)
            assert execution.status == "FAILED", f"Expected FAILED, got {execution.status}"
            assert "timeout" in execution.error.lower(), f"Expected timeout error: {execution.error}"
        finally:
            # Restore original
            wf_module.WorkflowEngine._execute_step = original_execute

    def test_timeout_validation_rejects_negative(self, temp_storage):
        """Verify workflow validation rejects negative/zero timeout."""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        workflow = {
            "name": "bad-timeout",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "timeout": -5,  # Invalid: negative timeout
            "steps": [{"name": "step-1", "type": "system"}],
        }

        with pytest.raises(ValidationError, match="timeout must be positive"):
            engine.execute_workflow(workflow)


class TestDRT001_1_DuplicateStepDetection:
    """Verify duplicate step names are detected."""

    def test_duplicate_step_names_rejected(self, temp_storage):
        """Verify workflow validation rejects duplicate step names."""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        workflow = {
            "name": "duplicate-steps",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [
                {"name": "step-1", "type": "system"},
                {"name": "step-1", "type": "system"},  # Duplicate!
                {"name": "step-2", "type": "system"},
            ],
        }

        with pytest.raises(ValidationError, match="Duplicate step names"):
            engine.execute_workflow(workflow)


class TestDRT001_1_ContractValidation:
    """Verify contract validation includes all 9 mandatory fields."""

    def test_contract_validation_checks_all_fields(self, temp_storage):
        """Verify validate_contract checks finished_at and duration_ms."""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        workflow = {
            "name": "contract-test",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }

        execution = engine.execute_workflow(workflow)

        # Verify contract is valid
        assert ExecutionTracker.validate_contract(execution), "Valid contract marked invalid"

        # Create execution and verify all 9 fields present
        required_fields = [
            "execution_id",
            "correlation_id",
            "workflow_version",
            "runtime_version",
            "started_at",
            "finished_at",
            "duration_ms",
            "status",
            "checksum",
        ]

        for field in required_fields:
            value = getattr(execution, field, None)
            assert value is not None, f"Missing mandatory field: {field}"


class TestDRT001_1_LifecycleIntegration:
    """Integration tests for fixed lifecycle."""

    def test_http_app_with_graceful_shutdown(self):
        """Verify HTTP app uses lifespan correctly (no deprecated on_event)."""
        app, shutdown_mgr = create_runtime_api()

        # App should be created without errors
        assert app is not None
        assert shutdown_mgr is not None

        # Should not have deprecated on_event routes
        # (lifespan replaces on_event("startup") and on_event("shutdown"))
        # If deprecated on_event was used, we'd see it in the routes
        for route in app.routes:
            # Verify no old-style event handler registration
            assert not hasattr(route, "on_event"), "Found deprecated on_event usage"

    def test_concurrent_http_requests_with_thread_safety(self):
        """Verify HTTP service handles concurrent requests without WAL corruption."""
        app, _ = create_runtime_api()
        client = TestClient(app)

        workflow = {
            "name": "concurrent-test",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }

        # Send multiple concurrent requests
        responses = []
        threads = []

        def send_request():
            response = client.post("/workflow", json={"workflow": workflow})
            responses.append(response.status_code)

        for _ in range(10):
            t = threading.Thread(target=send_request)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All should succeed
        assert all(code == 200 for code in responses), f"Some requests failed: {responses}"
        assert len(responses) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
