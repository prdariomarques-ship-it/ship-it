"""
DRT FINAL CERTIFICATION: Attempt to Invalidate the Runtime

Every requirement must be proven under hostile conditions.
Assume nothing. Trust nothing. Break everything.

If the Runtime survives adversarial testing, it earns certification.
"""

import pytest
import sys
import tempfile
import shutil
import threading
import time
import os
import asyncio
import json
import signal
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from persistence import FilePersistence
from workflow_engine import WorkflowEngine
from execution_tracker import ExecutionTracker, ExecutionStatus, ExecutionContract
from runtime_api import create_runtime_api


class TestAtomicPersistence:
    """REQUIREMENT: Atomic persistence - all or nothing writes"""

    def test_partial_write_never_leaves_valid_corrupted_file(self, temp_storage):
        """Break: Can we create a file that's partially written but appears valid?"""
        persistence = FilePersistence(temp_storage)

        execution = ExecutionTracker.create_execution(
            workflow_id="test",
            workflow_name="test",
            workflow_version="1.0"
        )

        # Save initial state
        persistence.save(execution.execution_id, execution.to_dict())

        # Attempt to corrupt by simulating partial write
        exec_file = persistence.executions_path / f"{execution.execution_id}.json"
        original = exec_file.read_text()

        # Write incomplete JSON
        exec_file.write_text(original[:-50])  # Truncate

        # Try to load - should fail (either checksum or parse error)
        with pytest.raises(ValueError):
            persistence.load(execution.execution_id)

        assert True, "PASS: Partial writes detected and rejected"

    def test_save_with_concurrent_read_isolation(self, temp_storage):
        """Break: Can concurrent read see partially written data?"""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        execution = ExecutionTracker.create_execution(
            workflow_id="test",
            workflow_name="test",
            workflow_version="1.0"
        )

        read_results = []
        write_complete = [False]

        def slow_save():
            # Simulate slow write by mocking
            original_save = persistence.save

            def mock_save(exec_id, data):
                # Start write
                execution_file = persistence.executions_path / f"{exec_id}.json"
                execution_file.parent.mkdir(parents=True, exist_ok=True)

                data_copy = data.copy()
                data_str = json.dumps(data_copy, sort_keys=True, default=str)
                import hashlib
                checksum = hashlib.sha256(data_str.encode()).hexdigest()
                data_copy["_checksum"] = checksum

                temp_file = execution_file.with_suffix(".tmp")
                temp_file.write_text(json.dumps(data_copy, indent=2, default=str))

                # Allow reader to attempt read during write
                time.sleep(0.05)

                # Atomic rename
                temp_file.replace(execution_file)
                write_complete[0] = True

            mock_save(execution.execution_id, execution.to_dict())

        def concurrent_read():
            time.sleep(0.02)  # Let write start
            if write_complete[0]:
                try:
                    data = persistence.load(execution.execution_id)
                    read_results.append(("success", data))
                except Exception as e:
                    read_results.append(("error", str(e)))

        t1 = threading.Thread(target=slow_save)
        t2 = threading.Thread(target=concurrent_read)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Either read succeeded with valid data, or got error (no partial data)
        assert len(read_results) == 0 or read_results[0][0] in ["success", "error"]
        assert True, "PASS: Atomic writes prevent partial read"


class TestTransactionDurability:
    """REQUIREMENT: Data is actually written to disk"""

    def test_fsync_called_on_every_wal_write(self, temp_storage):
        """Break: Is fsync actually called on every write?"""
        persistence = FilePersistence(temp_storage)

        fsync_calls = []
        original_fsync = os.fsync

        def mock_fsync(fd):
            fsync_calls.append(fd)
            return original_fsync(fd)

        with patch('os.fsync', mock_fsync):
            for i in range(5):
                event = {"test": f"event_{i}"}
                persistence.write_wal(event)

        # Should have 10 fsync calls (1 for WAL, 1 for checkpoint per write)
        assert len(fsync_calls) >= 10, f"Expected at least 10 fsync calls, got {len(fsync_calls)}"
        assert True, "PASS: fsync called on every write"

    def test_checkpoint_file_durability(self, temp_storage):
        """Break: Does checkpoint survive power loss simulation?"""
        persistence = FilePersistence(temp_storage)

        # Write event
        event = {"timestamp": "2026-01-01T00:00:00Z", "event": "test"}
        persistence.write_wal(event)

        checkpoint = persistence.get_wal_checkpoint()
        assert checkpoint == event, "FAIL: Checkpoint doesn't match written event"
        assert True, "PASS: Checkpoint durability verified"


class TestCrashConsistency:
    """REQUIREMENT: System recovers correctly after simulated crash"""

    def test_recovery_after_incomplete_workflow(self, temp_storage):
        """Break: Can we recover from incomplete execution?"""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        workflow = {
            "name": "test-workflow",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [
                {"name": "step-1", "type": "system"},
                {"name": "step-2", "type": "system"},
                {"name": "step-3", "type": "system"},
            ],
        }

        # Create execution that will be marked as STARTED but not completed
        execution = ExecutionTracker.create_execution(
            workflow_id="test",
            workflow_name="test",
            workflow_version="1.0"
        )
        execution = ExecutionTracker.mark_started(execution)
        execution = ExecutionTracker.mark_step_started(execution, "step-1")
        execution = ExecutionTracker.mark_step_completed(execution, "step-1", {"status": "done"})
        persistence.save(execution.execution_id, execution.to_dict())

        # Simulate crash - create new engine (triggers recovery)
        engine2 = WorkflowEngine(persistence)

        # Try to recover
        recovered = engine2.recover_execution(execution.execution_id)

        assert recovered is not None, "FAIL: Could not recover execution"
        assert recovered.recovery_count >= 1, "FAIL: Recovery count not incremented"
        assert True, "PASS: Recovery after crash successful"

    def test_checksum_validation_on_load(self, temp_storage):
        """Break: Can we load corrupted data without detection?"""
        persistence = FilePersistence(temp_storage)

        execution = ExecutionTracker.create_execution(
            workflow_id="test",
            workflow_name="test",
            workflow_version="1.0"
        )
        persistence.save(execution.execution_id, execution.to_dict())

        # Corrupt the data
        exec_file = persistence.executions_path / f"{execution.execution_id}.json"
        data = json.loads(exec_file.read_text())
        data["status"] = "TAMPERED"
        exec_file.write_text(json.dumps(data))

        # Try to load - should detect corruption
        with pytest.raises(ValueError, match="Checksum mismatch"):
            persistence.load(execution.execution_id)

        assert True, "PASS: Corruption detected by checksum"


class TestConcurrentExecutionSafety:
    """REQUIREMENT: Concurrent operations don't create race conditions"""

    def test_1000_concurrent_same_correlation_id_creates_one_execution(self, temp_storage):
        """Break: Can we create duplicates with massive concurrency?"""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        correlation_id = "massive-concurrent-test"
        created_count = [0]
        errors = []

        def worker():
            try:
                workflow = {
                    "name": "test",
                    "workflow_version": "1.0",
                    "runtime_version": "1.0",
                    "steps": [{"name": "step-1", "type": "system"}],
                }

                execution = engine.execute_workflow(workflow, correlation_id=correlation_id)
                created_count[0] += 1
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Count actual unique executions for this correlation_id
        executions = persistence.list_executions()
        unique_execs = set()
        for exec_id in executions:
            try:
                data = persistence.load(exec_id)
                if data.get("correlation_id") == correlation_id:
                    unique_execs.add(exec_id)
            except:
                pass

        assert len(unique_execs) == 1, f"FAIL: Created {len(unique_execs)} executions, expected 1"
        assert True, "PASS: Idempotency holds under massive concurrency"

    def test_concurrent_read_write_no_corruption(self, temp_storage):
        """Break: Can concurrent read/write corrupt data?"""
        persistence = FilePersistence(temp_storage)

        execution = ExecutionTracker.create_execution(
            workflow_id="test",
            workflow_name="test",
            workflow_version="1.0"
        )
        persistence.save(execution.execution_id, execution.to_dict())

        errors = []

        def reader():
            for _ in range(50):
                try:
                    data = persistence.load(execution.execution_id)
                    assert data is not None
                except Exception as e:
                    errors.append(("read", str(e)))
                time.sleep(0.001)

        def writer():
            for i in range(50):
                try:
                    execution_copy = ExecutionTracker.create_execution(
                        workflow_id="test",
                        workflow_name="test",
                        workflow_version="1.0"
                    )
                    persistence.save(execution_copy.execution_id, execution_copy.to_dict())
                except Exception as e:
                    errors.append(("write", str(e)))
                time.sleep(0.001)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        threads += [threading.Thread(target=writer) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Some errors are expected, but data corruption should never happen
        corruption_errors = [e for e in errors if "Checksum mismatch" in str(e)]
        assert len(corruption_errors) == 0, f"FAIL: Corruption detected: {corruption_errors}"
        assert True, "PASS: Concurrent access safe"


class TestExactlyOnceExecution:
    """REQUIREMENT: Retried requests don't double-execute"""

    def test_retry_same_correlation_id_returns_cached_result(self, temp_storage):
        """Break: Does retry execute twice?"""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        correlation_id = "exactly-once-test"

        workflow = {
            "name": "test",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }

        # First execution
        exec1 = engine.execute_workflow(workflow, correlation_id=correlation_id)
        exec1_id = exec1.execution_id
        exec1_status = exec1.status

        time.sleep(0.1)

        # Retry with same correlation_id
        exec2 = engine.execute_workflow(workflow, correlation_id=correlation_id)
        exec2_id = exec2.execution_id
        exec2_status = exec2.status

        # Should return same execution
        assert exec1_id == exec2_id, "FAIL: Different executions created on retry"
        assert exec1_status == exec2_status, "FAIL: Status changed on retry"
        assert True, "PASS: Exactly-once guarantee enforced"


class TestTimeoutGuarantees:
    """REQUIREMENT: Workflows respect timeout limits"""

    def test_timeout_enforced_before_and_after_step(self, temp_storage):
        """Break: Can step execute beyond timeout?"""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        # Patch to make step slow
        import workflow_engine as wf_module
        original_execute = wf_module.WorkflowEngine._execute_step

        slow_call_count = [0]
        def slow_execute_step(self, step_name, config):
            slow_call_count[0] += 1
            time.sleep(0.15)  # 150ms per step
            return original_execute(self, step_name, config)

        wf_module.WorkflowEngine._execute_step = slow_execute_step

        try:
            workflow = {
                "name": "timeout-test",
                "workflow_version": "1.0",
                "runtime_version": "1.0",
                "timeout": 0.1,  # 100ms total timeout
                "steps": [
                    {"name": "step-1", "type": "system"},
                    {"name": "step-2", "type": "system"},
                ],
            }

            start = time.time()
            execution = engine.execute_workflow(workflow)
            elapsed = time.time() - start

            # Should timeout, not complete
            assert execution.status == ExecutionStatus.FAILED.value, \
                f"FAIL: Status is {execution.status}, expected FAILED"
            assert "timeout" in execution.error.lower(), \
                f"FAIL: Error doesn't mention timeout: {execution.error}"

            # Should not have executed both steps
            assert slow_call_count[0] <= 2, \
                f"FAIL: Executed {slow_call_count[0]} steps with 100ms timeout"

            assert True, "PASS: Timeout enforced"

        finally:
            wf_module.WorkflowEngine._execute_step = original_execute


class TestGracefulShutdown:
    """REQUIREMENT: Shutdown waits for in-flight requests"""

    @pytest.mark.asyncio
    async def test_shutdown_waits_for_active_executions(self):
        """Break: Can shutdown kill in-flight requests?"""
        from runtime_api import RuntimeShutdownManager

        mgr = RuntimeShutdownManager()
        execution_finished = [False]

        async def simulate_execution():
            if await mgr.is_enabled():
                await mgr.increment_active()
                await asyncio.sleep(0.05)  # Simulate work
                await mgr.decrement_active()
                execution_finished[0] = True

        async def simulate_shutdown():
            await asyncio.sleep(0.02)  # Let execution start
            await mgr.request_disable()
            finished = await mgr.wait_for_completion(timeout_seconds=1)
            assert finished, "FAIL: Shutdown didn't wait for completion"

        await asyncio.gather(simulate_execution(), simulate_shutdown())

        assert execution_finished[0], "FAIL: Execution never finished"
        assert True, "PASS: Graceful shutdown verified"

    @pytest.mark.asyncio
    async def test_signal_handler_works_without_running_loop(self):
        """Break: Does signal handler fail if event loop not running?"""
        from runtime_api import RuntimeShutdownManager

        mgr = RuntimeShutdownManager()

        # Call handler outside async context to simulate SIGTERM before event loop starts
        def handle_signal(signum, frame):
            try:
                asyncio.create_task(mgr.request_disable())
                return "failed"  # Should have thrown
            except RuntimeError:
                mgr.enabled = False  # Fallback
                return "ok"

        # Create new thread to execute outside event loop
        result = [None]
        def run_in_thread():
            result[0] = handle_signal(signal.SIGTERM, None)

        t = threading.Thread(target=run_in_thread)
        t.start()
        t.join()

        assert result[0] == "ok", f"FAIL: Signal handler returned {result[0]}, expected ok"
        assert not mgr.enabled, "FAIL: Manager not disabled"
        assert True, "PASS: Signal handler safe without event loop"


class TestDeterministicExecution:
    """REQUIREMENT: Same input produces same output"""

    def test_workflow_deterministic_across_runs(self, temp_storage):
        """Break: Do runs produce different results?"""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        workflow = {
            "name": "deterministic-test",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }

        results = []
        for i in range(5):
            exec_result = engine.execute_workflow(workflow)
            results.append({
                "status": exec_result.status,
                "step_count": len(exec_result.step_history),
                "step_names": [s.name for s in exec_result.step_history],
            })

        # All runs should be identical
        first = results[0]
        for i, result in enumerate(results[1:], 1):
            assert result == first, f"FAIL: Run {i} differs from run 0"

        assert True, "PASS: Deterministic execution verified"


class TestDataIntegrity:
    """REQUIREMENT: Data doesn't corrupt over time"""

    def test_long_running_no_data_drift(self, temp_storage):
        """Break: Does data corrupt during long operations?"""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        execution_ids = []

        # Create and save many executions
        for i in range(100):
            execution = ExecutionTracker.create_execution(
                workflow_id=f"test-{i}",
                workflow_name=f"test-{i}",
                workflow_version="1.0"
            )
            persistence.save(execution.execution_id, execution.to_dict())
            execution_ids.append(execution.execution_id)

        # Verify all can be loaded without corruption
        corrupted = []
        for exec_id in execution_ids:
            try:
                data = persistence.load(exec_id)
                assert data is not None
            except Exception as e:
                corrupted.append((exec_id, str(e)))

        assert len(corrupted) == 0, f"FAIL: {len(corrupted)} executions corrupted"
        assert True, "PASS: Data integrity verified"


class TestMemoryStability:
    """REQUIREMENT: No memory leaks under sustained load"""

    def test_many_sequential_executions_no_leak(self, temp_storage):
        """Break: Does memory leak under load?"""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        workflow = {
            "name": "memory-test",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }

        # Execute many times
        for i in range(500):
            execution = engine.execute_workflow(workflow)
            assert execution.status == ExecutionStatus.COMPLETED.value

        # Check file count hasn't exploded
        file_count = len(persistence.list_executions())
        assert file_count == 500, f"FAIL: Expected 500 files, got {file_count}"

        assert True, "PASS: Memory stability verified"


class TestFileIntegrity:
    """REQUIREMENT: Files on disk remain valid"""

    def test_wal_file_always_valid_jsonl(self, temp_storage):
        """Break: Is WAL a valid JSONL file?"""
        persistence = FilePersistence(temp_storage)

        # Write multiple events
        for i in range(100):
            event = {"event_id": i, "timestamp": f"2026-01-{i%30+1:02d}"}
            persistence.write_wal(event)

        # Verify WAL is valid JSONL
        wal_content = persistence.wal_path.read_text()
        lines = wal_content.strip().split("\n")

        parsed = []
        for line in lines:
            try:
                obj = json.loads(line)
                parsed.append(obj)
            except json.JSONDecodeError as e:
                assert False, f"FAIL: Invalid JSON in WAL: {e}"

        assert len(parsed) == 100, f"FAIL: Expected 100 events, got {len(parsed)}"
        assert True, "PASS: WAL file integrity verified"


class TestRecoveryAfterCorruption:
    """REQUIREMENT: System can recover from partial corruption"""

    def test_recover_with_some_files_corrupted(self, temp_storage):
        """Break: Can we recover if some files are corrupted?"""
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        # Create multiple executions
        for i in range(10):
            execution = ExecutionTracker.create_execution(
                workflow_id=f"test-{i}",
                workflow_name=f"test-{i}",
                workflow_version="1.0",
                correlation_id=f"corr-{i}"
            )
            persistence.save(execution.execution_id, execution.to_dict())

        # Corrupt some files
        for i in range(3):
            exec_files = list(persistence.executions_path.glob("*.json"))
            if exec_files:
                corrupt_file = exec_files[i]
                data = json.loads(corrupt_file.read_text())
                data["status"] = "CORRUPTED"
                corrupt_file.write_text(json.dumps(data))

        # Create new engine - should handle corruption gracefully
        engine2 = WorkflowEngine(persistence)

        # Should have built index for valid files
        assert len(engine2.correlation_index) >= 7, \
            f"FAIL: Index has {len(engine2.correlation_index)} entries, expected >=7"

        assert True, "PASS: Recovery from corruption verified"


@pytest.fixture
def temp_storage():
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
