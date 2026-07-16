from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from auth.dependencies import CurrentUser
from workflows.service import WorkflowError, workflow_service

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowTriggerRequest(BaseModel):
    payload: dict = {}


class WorkflowTriggerResponse(BaseModel):
    workflow: str
    result: dict


@router.post("/{workflow_name}/trigger", response_model=WorkflowTriggerResponse)
async def trigger_workflow(
    workflow_name: str, payload: WorkflowTriggerRequest, _: CurrentUser
) -> WorkflowTriggerResponse:
    try:
        result = await workflow_service.trigger(workflow_name, payload.payload)
    except WorkflowError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return WorkflowTriggerResponse(workflow=workflow_name, result=result)
