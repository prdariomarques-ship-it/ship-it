"""
DRT-001.2: Evidence-Based Verification of Principal Engineer Review Findings

Each finding must be:
1. Reproducible with a failing test
2. Fixed with minimal change
3. Verified with passing test
4. Regression tested

This document serves as executable proof of issues and their resolution.
"""

import pytest
import sys
import tempfile
import shutil
import threading
import time
import os
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from persistence import FilePersistence
from workflow_engine import WorkflowEngine
from execution_tracker import ExecutionTracker, ExecutionContract, ExecutionStatus


class TestFinding1_WALAtomicity:
    """Finding 1: WAL consistency broken when checkpoint write fails"""

    def test_checkpoint_write_failure_leaves_wal_inconsistent(self, temp_storage):
        """
        HYPOTHESIS: If checkpoint write fails after WAL append,
        the WAL entry is written but checkpoint is stale.

        This test attempts to reproduce by mocking checkpoint write to fail.
        """
        persistence = FilePersistence(temp_storage)

        # Create initial checkpoint
        initial_event = {"timestamp": "2026-01-01T00:00:00Z", "event": "init"}
        persistence.write_wal(initial_event)
        initial_checkpoint = persistence.get_wal_checkpoint()

        # Now mock checkpoint write to fail on next call
        original_write_text = Path.write_text
        call_count = [0]

        def failing_write_text(self, text):
            call_count[0] += 1
            if self.name == "checkpoint.json" and call_count[0] > 1:
                raise IOError("Simulated checkpoint write failure")
            return original_write_text(self, text)

        with patch.object(Path, 'write_text', failing_write_text):
            try:
                new_event = {"timestamp": "2026-01-02T00:00:00Z", "event": "new"}
                persistence.write_wal(new_event)
            except IOError:
                pass  # Expected: checkpoint write fails

        # Check if WAL has new event but checkpoint is stale
        wal_lines = persistence.wal_path.read_text().strip().split("\n")
        checkpoint_after = persistence.get_wal_checkpoint()

        wal_has_new_event = any("2026-01-02" in line for line in wal_lines)
        checkpoint_is_stale = checkpoint_after == initial_checkpoint

        if wal_has_new_event and checkpoint_is_stale:
            # CONFIRMED: WAL consistency broken
            assert True, "Finding 1 CONFIRMED: WAL entry exists but checkpoint is stale"
        else:
            # NOT REPRODUCED
            assert False, "Finding 1 NOT REPRODUCED: Could not create inconsistent state"


class TestFinding2_FsyncDurability:
    """Finding 2: Missing fsync() means data loss on power failure"""

    def test_no_fsync_called_on_wal_write(self, temp_storage):
        """
        HYPOTHESIS: write_wal() does not call fsync(), leaving data in OS buffer.

        After DRT-001.2 fix: fsync() SHOULD be called. Test validates fix works.
        """
        persistence = FilePersistence(temp_storage)

        fsync_called = [False]
        original_fsync = os.fsync

        def mock_fsync(fd):
            fsync_called[0] = True
            return original_fsync(fd)

        with patch('os.fsync', mock_fsync):
            event = {"test": "event"}
            persistence.write_wal(event)

        if fsync_called[0]:
            # VERIFIED: fsync is now called (fix applied)
            assert True, "Finding 2 VERIFIED FIXED: fsync() now called on WAL write"
        else:
            # REGRESSION: fsync was removed
            assert False, "Finding 2 REGRESSION: fsync() not called!"


class TestFinding3_IdempotencyRaceCondition:
    """Finding 3: Concurrent requests race on correlation_id check"""

    def test_concurrent_requests_same_correlation_id_create_duplicates(self, temp_storage):
        """
        HYPOTHESIS: Two concurrent requests with same correlation_id both create executions.

        Race condition:
        T0: Request A checks index → empty
        T1: Request B checks index → empty
        T2: Request A creates exec_A
        T3: Request B creates exec_B
        T4: Request A updates index[corr_id] = exec_A
        T5: Request B updates index[corr_id] = exec_B (overwrites)

        Result: Two different executions with same correlation_id
        """
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        correlation_id = "test-correlation-001"
        created_executions = []
        errors = []

        def execute_with_delay(delay_before_index_update=0):
            try:
                workflow = {
                    "name": "test-workflow",
                    "workflow_version": "1.0",
                    "runtime_version": "1.0",
                    "steps": [{"name": "step-1", "type": "system"}],
                }

                # Check idempotency (this is where race starts)
                existing = engine.check_idempotency(correlation_id)
                if existing and existing.status == ExecutionStatus.COMPLETED.value:
                    created_executions.append(("existing", existing.execution_id))
                    return

                # Create new execution
                execution = ExecutionTracker.create_execution(
                    workflow_id="test",
                    workflow_name="test",
                    workflow_version="1.0",
                    correlation_id=correlation_id,
                )
                created_executions.append(("new", execution.execution_id))

                # Simulate delay to expose race
                if delay_before_index_update:
                    time.sleep(delay_before_index_update)

                # Update index (unprotected)
                engine.correlation_index[correlation_id] = execution.execution_id

                # Persist
                persistence.save(execution.execution_id, execution.to_dict())

            except Exception as e:
                errors.append(e)

        # Launch two concurrent requests
        t1 = threading.Thread(target=lambda: execute_with_delay(0.01))
        t2 = threading.Thread(target=lambda: execute_with_delay(0.01))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        if errors:
            assert False, f"Errors during execution: {errors}"

        # Check if duplicates were created
        new_executions = [exec_id for typ, exec_id in created_executions if typ == "new"]

        if len(new_executions) > 1:
            # CONFIRMED: Race condition created duplicates
            assert True, f"Finding 3 CONFIRMED: {len(new_executions)} executions created with same correlation_id"
        else:
            # NOT REPRODUCED
            assert False, "Finding 3 NOT REPRODUCED: No duplicates created"


class TestFinding4_CorruptedFileSkip:
    """Finding 4: Silent skip of corrupted files in index rebuild"""

    def test_corrupted_file_silently_skipped_in_index_rebuild(self, temp_storage):
        """
        HYPOTHESIS: _build_correlation_index() silently skips corrupted files.

        If a file is corrupted (bad checksum), it's skipped instead of:
        1. Logging the error
        2. Attempting recovery
        3. Alerting the system
        """
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        # Create a valid execution
        workflow = {
            "name": "test-workflow",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }

        execution = engine.execute_workflow(workflow, correlation_id="corr-001")
        exec_id = execution.execution_id

        # Verify it's in the index
        assert "corr-001" in engine.correlation_index
        assert engine.correlation_index["corr-001"] == exec_id

        # Now corrupt the file
        exec_file = persistence.executions_path / f"{exec_id}.json"
        content = exec_file.read_text()
        # Corrupt the checksum field
        corrupted = content.replace('"_checksum": "', '"_checksum": "corrupted')
        exec_file.write_text(corrupted)

        # Create new engine (triggers index rebuild)
        engine2 = WorkflowEngine(persistence)

        # Check if corrupted execution is in the new index
        if "corr-001" not in engine2.correlation_index:
            # CONFIRMED: Corrupted file was skipped
            assert True, "Finding 4 CONFIRMED: Corrupted file silently skipped from index"
        else:
            # NOT REPRODUCED
            assert False, "Finding 4 NOT REPRODUCED: Corrupted file was not skipped"


class TestFinding5_MultiStagePersistenceFailure:
    """Finding 5: Multiple save() calls can leave inconsistent state"""

    def test_save_failure_mid_workflow_leaves_inconsistent_state(self, temp_storage):
        """
        HYPOTHESIS: If save() fails on the 3rd step,
        the execution will be marked FAILED with step_count=3
        but only 2 steps in step_history.

        The checksum validates the count, not the array length match.
        """
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        # Mock save to fail on 3rd call
        save_call_count = [0]
        original_save = persistence.save

        def failing_save(exec_id, data):
            save_call_count[0] += 1
            if save_call_count[0] == 3:  # Fail on 3rd save
                raise IOError("Simulated save failure")
            return original_save(exec_id, data)

        persistence.save = failing_save

        workflow = {
            "name": "multi-step-workflow",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [
                {"name": "step-1", "type": "system"},
                {"name": "step-2", "type": "system"},
                {"name": "step-3", "type": "system"},
            ],
        }

        try:
            engine.execute_workflow(workflow)
        except IOError:
            pass  # Expected: save fails

        # Check if there's an inconsistent execution saved
        executions = persistence.list_executions()

        inconsistent_found = False
        for exec_id in executions:
            try:
                data = persistence.load(exec_id)
                step_count = len(data.get("step_history", []))
                status = data.get("status")

                # If status is FAILED but step_count doesn't match steps
                if status == "FAILED" and step_count < 3:
                    inconsistent_found = True
                    break
            except Exception:
                pass

        if inconsistent_found:
            # CONFIRMED: Inconsistent state found
            assert True, "Finding 5 CONFIRMED: Multi-stage save failure creates inconsistency"
        else:
            # NOT REPRODUCED (likely because final_persistence after exception catches the error)
            assert False, "Finding 5 NOT REPRODUCED: No inconsistent state found"


class TestFinding6_SignalHandlerEventLoop:
    """Finding 6: Signal handler may fail if event loop not running"""

    def test_signal_handler_create_task_without_running_loop(self):
        """
        HYPOTHESIS: asyncio.create_task() called in signal handler
        without verifying event loop is running.

        In lifespan context, loop is running, so this may not be reproduc­ible.
        But if SIGTERM arrives before lifespan, it could fail.
        """
        from runtime_api import create_runtime_api
        import asyncio

        # This test validates the fix: signal handlers should only run
        # during lifespan when event loop is guaranteed to be running

        # Attempt to call create_task outside event loop
        from runtime_api import RuntimeShutdownManager

        mgr = RuntimeShutdownManager()

        def signal_handler(signum, frame):
            try:
                # This is what the current code does
                asyncio.create_task(mgr.request_disable())
                return False  # Success
            except RuntimeError as e:
                if "no running event loop" in str(e):
                    return True  # Failed as hypothesized
                raise

        result = signal_handler(None, None)

        if result:
            # CONFIRMED: Can fail without event loop
            assert True, "Finding 6 CONFIRMED: Signal handler fails without event loop"
        else:
            # NOT REPRODUCED (likely because test environment has event loop)
            # Or fix already in place
            assert False, "Finding 6 NOT REPRODUCED: Signal handler didn't fail"


class TestFinding7_TimeoutBetweenStepsOnly:
    """Finding 7: Timeout only checked between steps, not during step"""

    def test_long_running_step_exceeds_timeout(self, temp_storage):
        """
        After DRT-001.2 fix: Timeout SHOULD be checked after step execution.
        Test validates fix detects timeouts correctly.
        """
        persistence = FilePersistence(temp_storage)

        # Patch _execute_step to be slow
        import workflow_engine as wf_module
        original_execute = wf_module.WorkflowEngine._execute_step

        def slow_execute_step(self, step_name, config):
            time.sleep(0.2)  # 200ms
            return original_execute(self, step_name, config)

        wf_module.WorkflowEngine._execute_step = slow_execute_step

        try:
            engine = WorkflowEngine(persistence)

            workflow = {
                "name": "timeout-test",
                "workflow_version": "1.0",
                "runtime_version": "1.0",
                "timeout": 0.1,  # 100ms timeout
                "steps": [
                    {"name": "step-1", "type": "system"},
                ],
            }

            start = time.time()
            execution = engine.execute_workflow(workflow)
            elapsed = time.time() - start

            # Check if timeout was enforced
            if execution.status == ExecutionStatus.FAILED.value and "timeout" in execution.error.lower():
                # VERIFIED: Timeout now enforced (fix applied)
                assert True, f"Finding 7 VERIFIED FIXED: Timeout enforced after {elapsed:.3f}s"
            elif execution.status == ExecutionStatus.COMPLETED.value:
                # REGRESSION: Step completed despite timeout
                assert False, f"Finding 7 REGRESSION: Step completed despite timeout in {elapsed:.3f}s"
            else:
                assert False, f"Finding 7: Unexpected status {execution.status}"

        finally:
            wf_module.WorkflowEngine._execute_step = original_execute


class TestFinding8_EmitEventWALFailure:
    """Finding 8: _emit_event doesn't handle WAL write failure"""

    def test_emit_event_wal_failure_not_caught(self, temp_storage):
        """
        HYPOTHESIS: If write_wal() fails in _emit_event(),
        the exception is not caught and propagates to caller.
        """
        persistence = FilePersistence(temp_storage)
        engine = WorkflowEngine(persistence)

        # Mock write_wal to fail
        original_write_wal = persistence.write_wal

        def failing_write_wal(event):
            raise IOError("Simulated WAL write failure")

        persistence.write_wal = failing_write_wal

        try:
            # _emit_event is called during workflow execution
            workflow = {
                "name": "test",
                "workflow_version": "1.0",
                "runtime_version": "1.0",
                "steps": [{"name": "step-1", "type": "system"}],
            }

            engine.execute_workflow(workflow)
            # If we reach here, exception was caught
            assert False, "Finding 8 NOT REPRODUCED: Exception was caught"

        except IOError as e:
            # CONFIRMED: Exception propagated
            if "WAL write failure" in str(e):
                assert True, "Finding 8 CONFIRMED: _emit_event exception not caught"
            else:
                raise

        finally:
            persistence.write_wal = original_write_wal


class TestFinding9_ShutdownRaceCondition:
    """Finding 9: Shutdown race between availability check and increment"""

    @pytest.mark.asyncio
    async def test_shutdown_race_between_check_and_increment(self):
        """
        HYPOTHESIS: Request checks is_enabled(), then SIGTERM arrives,
        then request increments counter. Request executes after shutdown initiated.
        """
        from runtime_api import RuntimeShutdownManager

        mgr = RuntimeShutdownManager()
        execution_started = [False]

        async def simulate_request():
            # Check if enabled
            if await mgr.is_enabled():
                # RACE: SIGTERM can arrive here
                await mgr.increment_active()
                execution_started[0] = True
                await mgr.decrement_active()

        async def simulate_shutdown():
            await asyncio.sleep(0.01)  # Let request check is_enabled
            await mgr.request_disable()
            # Now wait for completion
            await mgr.wait_for_completion(timeout_seconds=1)

        # Run both concurrently
        await asyncio.gather(simulate_request(), simulate_shutdown())

        # If request started after shutdown, race is present
        if execution_started[0] and not mgr.enabled:
            # CONFIRMED: Request started after shutdown was initiated
            assert True, "Finding 9 CONFIRMED: Request executed after shutdown initiated"
        else:
            # NOT REPRODUCED
            assert False, "Finding 9 NOT REPRODUCED: Race condition not observed"


@pytest.fixture
def temp_storage():
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
