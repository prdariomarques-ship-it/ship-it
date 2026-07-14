"""
HTTP Runtime for DRT-001.
Production-grade HTTP service with graceful shutdown.
Three endpoints: POST /workflow, GET /workflow/{id}, GET /health.
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ValidationError as PydanticValidationError
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import signal
import asyncio
import time
import os
import sys
from datetime import datetime

from workflow_engine import WorkflowEngine, ValidationError as WorkflowValidationError
from persistence import FilePersistence
from execution_tracker import ExecutionStatus, ExecutionContract


class WorkflowRequest(BaseModel):
    """Workflow execution request."""
    workflow: Dict[str, Any]
    correlation_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    runtime_version: str
    uptime_seconds: int
    storage_valid: bool


class RuntimeShutdownManager:
    """Manages graceful shutdown."""

    def __init__(self):
        self.enabled = True
        self.active_executions = 0
        self._lock = asyncio.Lock()

    async def request_disable(self):
        """Disable new requests (SIGTERM received)."""
        async with self._lock:
            self.enabled = False

    async def is_enabled(self) -> bool:
        """Check if Runtime accepts new requests."""
        async with self._lock:
            return self.enabled

    async def increment_active(self):
        """Track active execution."""
        async with self._lock:
            self.active_executions += 1

    async def decrement_active(self):
        """Execution finished."""
        async with self._lock:
            self.active_executions -= 1

    async def wait_for_completion(self, timeout_seconds: int = 30):
        """Wait for active executions to finish."""
        start = time.time()
        while time.time() - start < timeout_seconds:
            async with self._lock:
                if self.active_executions == 0:
                    return True
            await asyncio.sleep(0.1)
        return False


def create_runtime_api(base_path: str = ".runtime") -> tuple:
    """Create FastAPI runtime application with graceful shutdown."""
    shutdown_mgr = RuntimeShutdownManager()

    # Initialize components
    persistence = FilePersistence(base_path)
    engine = WorkflowEngine(persistence)

    # Lifespan context manager for startup/shutdown
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        if not persistence.validate_storage():
            raise RuntimeError("Storage validation failed - cannot start Runtime")

        app._start_time = time.time()
        app._shutdown_mgr = shutdown_mgr

        # Register SIGTERM/SIGINT handlers for graceful shutdown
        def handle_sigterm(signum, frame):
            """Handle SIGTERM: trigger graceful shutdown."""
            try:
                asyncio.create_task(shutdown_mgr.request_disable())
            except RuntimeError:
                # Event loop not running; set flag directly (fallback)
                shutdown_mgr.enabled = False

        def handle_sigint(signum, frame):
            """Handle SIGINT: same as SIGTERM."""
            try:
                asyncio.create_task(shutdown_mgr.request_disable())
            except RuntimeError:
                # Event loop not running; set flag directly (fallback)
                shutdown_mgr.enabled = False

        signal.signal(signal.SIGTERM, handle_sigterm)
        signal.signal(signal.SIGINT, handle_sigint)

        yield

        # Shutdown
        await shutdown_mgr.request_disable()
        finished = await shutdown_mgr.wait_for_completion(timeout_seconds=30)

    app = FastAPI(title="DRT-001 Runtime", version="1.0", lifespan=lifespan)

    @app.post("/workflow")
    async def execute_workflow(
        request: WorkflowRequest,
        dry_run: bool = Query(False),
    ) -> Dict[str, Any]:
        """
        Execute a workflow.
        If dry_run=true, only parse, validate, compile (no execution).
        """
        # Check if Runtime is accepting new requests
        if not await shutdown_mgr.is_enabled():
            raise HTTPException(
                status_code=503,
                detail="Runtime is shutting down - new requests not accepted",
            )

        # Validate input
        if not request.workflow:
            raise HTTPException(status_code=400, detail="workflow is required")

        try:
            await shutdown_mgr.increment_active()

            if dry_run:
                # Dry run: parse, validate, compile, plan (no execution)
                result = engine.dry_run(request.workflow)
                return result

            # Full execution
            try:
                execution = engine.execute_workflow(
                    request.workflow,
                    correlation_id=request.correlation_id,
                )

                return {
                    "execution_id": execution.execution_id,
                    "correlation_id": execution.correlation_id,
                    "status": execution.status,
                    "workflow_version": execution.workflow_version,
                    "runtime_version": execution.runtime_version,
                    "started_at": execution.started_at,
                    "finished_at": execution.finished_at,
                    "duration_ms": execution.duration_ms,
                    "step_count": len(execution.step_history),
                }

            except WorkflowValidationError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Workflow execution failed: {str(e)}",
                )

        finally:
            await shutdown_mgr.decrement_active()

    @app.get("/workflow/{execution_id}")
    async def get_workflow(execution_id: str) -> Dict[str, Any]:
        """Get workflow execution status and results."""
        if not execution_id or len(execution_id) == 0:
            raise HTTPException(status_code=400, detail="execution_id required")

        try:
            # Try to recover first (in case of crash)
            execution = engine.recover_execution(execution_id)

            if not execution:
                # Try loading normally
                try:
                    data = persistence.load(execution_id)
                    if not data:
                        raise HTTPException(
                            status_code=404, detail=f"Execution {execution_id} not found"
                        )
                    execution = ExecutionContract.from_dict(data)
                except ValueError as e:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Corrupted execution data: {str(e)}",
                    )

            return {
                "execution_id": execution.execution_id,
                "correlation_id": execution.correlation_id,
                "status": execution.status,
                "workflow_version": execution.workflow_version,
                "runtime_version": execution.runtime_version,
                "workflow_name": execution.workflow_name,
                "started_at": execution.started_at,
                "finished_at": execution.finished_at,
                "duration_ms": execution.duration_ms,
                "step_history": [
                    {
                        "name": step.name,
                        "status": step.status,
                        "started_at": step.started_at,
                        "finished_at": step.finished_at,
                        "duration_ms": step.duration_ms,
                        "result": step.result,
                        "error": step.error,
                    }
                    for step in execution.step_history
                ],
                "recovery_count": execution.recovery_count,
                "retry_count": execution.retry_count,
                "audit_trail": execution.audit_trail,
                "error": execution.error,
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        """Health check endpoint with runtime status."""
        start_time = getattr(app, "_start_time", time.time())
        uptime = int(time.time() - start_time)
        storage_valid = persistence.validate_storage()

        return {
            "status": "healthy" if storage_valid else "degraded",
            "runtime_version": "1.0",
            "uptime_seconds": uptime,
            "storage_valid": storage_valid,
            "accepting_requests": await shutdown_mgr.is_enabled(),
            "active_executions": shutdown_mgr.active_executions,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    return app, shutdown_mgr




if __name__ == "__main__":
    import uvicorn

    # Check if DRT_ENABLED environment variable
    if os.environ.get("DRT_ENABLED", "true").lower() == "false":
        print("Runtime disabled (DRT_ENABLED=false)")
        sys.exit(0)

    # Create app (shutdown_mgr is created internally)
    app, shutdown_mgr = create_runtime_api()

    # Run server
    print("Starting DRT-001 Runtime...")
    print("Listening on http://0.0.0.0:5000")
    print("Endpoints: POST /workflow, GET /workflow/{id}, GET /health")
    print("Send SIGTERM to gracefully shutdown")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=5000,
        log_level="info",
    )
