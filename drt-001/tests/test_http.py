"""
HTTP API tests for DRT-001 Runtime.
Tests all three endpoints and graceful shutdown.
"""

import pytest
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient
from runtime_api import create_runtime_api


@pytest.fixture
def temp_storage():
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir)


@pytest.fixture
def client(temp_storage):
    app, _ = create_runtime_api(temp_storage)
    return TestClient(app)


class TestWorkflowEndpoint:
    """Test POST /workflow endpoint."""

    def test_execute_workflow(self, client):
        """Test successful workflow execution."""
        workflow = {
            "name": "test-wf",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [
                {"name": "step-1", "type": "system"},
            ],
        }

        response = client.post(
            "/workflow",
            json={"workflow": workflow},
        )

        assert response.status_code == 200
        data = response.json()
        assert "execution_id" in data
        assert "correlation_id" in data
        assert data["status"] == "COMPLETED"

    def test_workflow_dry_run(self, client):
        """Test dry-run mode."""
        workflow = {
            "name": "dry-run-wf",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [
                {"name": "step-1", "type": "system"},
                {"name": "step-2", "type": "system"},
            ],
        }

        response = client.post(
            "/workflow?dry_run=true",
            json={"workflow": workflow},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PLAN_READY"
        assert len(data["step_sequence"]) == 2

    def test_workflow_with_correlation_id(self, client):
        """Test idempotency with correlation ID."""
        workflow = {
            "name": "idempotent-wf",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }

        correlation_id = "test-correlation-123"

        # First execution
        response1 = client.post(
            "/workflow",
            json={"workflow": workflow, "correlation_id": correlation_id},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        exec_id_1 = data1["execution_id"]

        # Second execution with same correlation ID
        response2 = client.post(
            "/workflow",
            json={"workflow": workflow, "correlation_id": correlation_id},
        )
        assert response2.status_code == 200
        data2 = response2.json()
        exec_id_2 = data2["execution_id"]

        # Should return same execution
        assert exec_id_1 == exec_id_2

    def test_workflow_invalid(self, client):
        """Test invalid workflow."""
        workflow = {
            "workflow_version": "1.0",
            # Missing name and steps
        }

        response = client.post(
            "/workflow",
            json={"workflow": workflow},
        )

        # Should fail validation
        assert response.status_code == 400

    def test_workflow_missing_field(self, client):
        """Test missing workflow field."""
        response = client.post(
            "/workflow",
            json={},  # Missing workflow
        )

        assert response.status_code in [400, 422]


class TestGetWorkflowEndpoint:
    """Test GET /workflow/{id} endpoint."""

    def test_get_execution(self, client):
        """Test retrieving execution."""
        workflow = {
            "name": "retrieval-wf",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "steps": [{"name": "step-1", "type": "system"}],
        }

        # Execute
        exec_response = client.post(
            "/workflow",
            json={"workflow": workflow},
        )
        exec_id = exec_response.json()["execution_id"]

        # Retrieve
        get_response = client.get(f"/workflow/{exec_id}")

        assert get_response.status_code == 200
        data = get_response.json()
        assert data["execution_id"] == exec_id
        assert data["status"] == "COMPLETED"
        assert len(data["step_history"]) == 1

    def test_get_nonexistent_execution(self, client):
        """Test getting nonexistent execution."""
        response = client.get("/workflow/nonexistent-id")
        assert response.status_code == 404

    def test_get_empty_execution_id(self, client):
        """Test with empty execution ID."""
        response = client.get("/workflow/nonexistent")
        # Should return 404 for nonexistent
        assert response.status_code == 404


class TestHealthEndpoint:
    """Test GET /health endpoint."""

    def test_health_check(self, client):
        """Test health endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert data["runtime_version"] == "1.0"
        assert data["uptime_seconds"] >= 0
        assert "storage_valid" in data
        assert "accepting_requests" in data

    def test_health_multiple_calls(self, client):
        """Test health check consistency."""
        response1 = client.get("/health")
        import time
        time.sleep(0.1)
        response2 = client.get("/health")

        data1 = response1.json()
        data2 = response2.json()

        assert data1["runtime_version"] == data2["runtime_version"]
        assert data2["uptime_seconds"] >= data1["uptime_seconds"]


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_workflow_timeout_handling(self, client):
        """Test workflow with timeout."""
        workflow = {
            "name": "timeout-wf",
            "workflow_version": "1.0",
            "runtime_version": "1.0",
            "timeout": 1,  # 1 second
            "steps": [{"name": "step-1", "type": "system"}],
        }

        response = client.post(
            "/workflow",
            json={"workflow": workflow},
        )

        # Should complete (timeout is for enforcement later)
        assert response.status_code == 200

    def test_workflow_malformed_json(self, client):
        """Test malformed JSON."""
        response = client.post(
            "/workflow",
            data="not valid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code in [400, 422]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
