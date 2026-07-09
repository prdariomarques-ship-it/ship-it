"""Trigger n8n workflows over their webhook endpoints."""
import httpx

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class WorkflowError(RuntimeError):
    pass


class WorkflowService:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def trigger(self, workflow: str, payload: dict) -> dict:
        """POST the payload to n8n at <base>/webhook/<workflow>."""
        url = f"{self._settings.n8n_base_url}/webhook/{workflow}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                if response.headers.get("content-type", "").startswith("application/json"):
                    return response.json()
                return {"status": "ok"}
        except httpx.HTTPError as exc:
            logger.error("n8n workflow %s failed: %s", workflow, exc)
            raise WorkflowError(f"Workflow {workflow!r} could not be triggered") from exc


workflow_service = WorkflowService()
