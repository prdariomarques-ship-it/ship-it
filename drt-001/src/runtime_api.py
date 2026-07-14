"""
HTTP API for DRT-001 Runtime.
Three endpoints: POST /workflow, GET /workflow/{id}, GET /health.
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any
import yaml
import os

from workflow_engine import WorkflowEngine, ValidationError
from persistence import FilePersistence
from execution_tracker import ExecutionStatus


class WorkflowRequest(BaseModel):
    """Workflow execution request."""
    workflow: Dict[str, Any]
    correlation_id: Optional[str] = None


class WorkflowResponse(BaseModel):
    """Workflow execution response."""
    execution_id: str
    correlation_id: str
    status: str
    message: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    runtime_version: str
    uptime_seconds: int
    storage_valid: bool


def create_runtime_api(base_path: str = ".runtime") -> FastAPI:
    """Create FastAPI runtime application."""
    app = FastAPI(title="DRT-001 Runtime", version="1.0")

    # Initialize components
    persistence = FilePersistence(base_path)
    engine = WorkflowEngine(persistence)

    # Startup validation
    @app.on_event("startup")
    async def startup():
        """Validate storage on startup."""
        if not persistence.validate_storage():
            raise RuntimeError("Storage validation failed")

    @app.post("/workflow")
    async def execute_workflow(
        request: WorkflowRequest,
        dry_run: bool = Query(False),
    ) -> Dict[str, Any]:
        """
        Execute a workflow.
        If dry_run=true, only parse, validate, compile (no execution).
        """
        try:
            if dry_run:
                # Dry run: parse, validate, compile, plan
                result = engine.dry_run(request.workflow)
                return result

            # Full execution
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

        except ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/workflow/{execution_id}")
    async def get_workflow(execution_id: str) -> Dict[str, Any]:
        """Get workflow execution status and results."""
        try:
            # Try to recover first (in case of crash)
            execution = engine.recover_execution(execution_id)

            if not execution:
                # Try loading normally
                data = persistence.load(execution_id)
                if not data:
                    raise HTTPException(
                        status_code=404, detail=f"Execution {execution_id} not found"
                    )
                from execution_tracker import ExecutionContract
                execution = ExecutionContract.from_dict(data)

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
        """Health check endpoint."""
        import time
        from datetime import datetime

        start_time = getattr(app, "_start_time", time.time())
        uptime = int(time.time() - start_time)

        return {
            "status": "healthy" if persistence.validate_storage() else "degraded",
            "runtime_version": "1.0",
            "uptime_seconds": uptime,
            "storage_valid": persistence.validate_storage(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    # Store start time
    app._start_time = __import__("time").time()

    return app


if __name__ == "__main__":
    import uvicorn

    # Check if DRT_ENABLED is set
    if os.environ.get("DRT_ENABLED", "true").lower() == "false":
        print("Runtime disabled (DRT_ENABLED=false)")
        exit(0)

    app = create_runtime_api()
    uvicorn.run(app, host="0.0.0.0", port=8000)
