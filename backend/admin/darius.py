"""Admin panel -> DARIUS OSS bridge (tasks, results, human decisions).

The panel is an *operator console*: it reads task state from DARIUS and relays
the operator's approve / reject / cancel decision. It owns no queue, no
scheduler and no approval logic -- DARIUS validates every decision where the
action executes. Every decision is audited here with the Dario OS admin user
(DARIUS itself only knows the operator credential).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.permissions import require_admin
from database.session import get_db
from models.user import User
from services import darius_client as dc
from services.audit import record_log
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/admin/darius", tags=["admin"], dependencies=[Depends(require_admin)]
)

DbSession = Annotated[AsyncSession, Depends(get_db)]
AdminUser = Annotated[User, Depends(require_admin)]

TaskStatusFilter = Literal["PENDING", "QUEUED", "RUNNING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"]


def operator_client() -> dc.DariusClient:
    """Dependency seam: tests (and future multi-tenant wiring) override this."""
    return dc.get_operator_client()


Operator = Annotated[dc.DariusClient, Depends(operator_client)]


class RejectBody(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class DariusStatus(BaseModel):
    configured: bool
    reachable: bool
    circuit: str
    latency_ms: float | None = None
    base_url: str
    service_credential_configured: bool
    operator_credential_configured: bool
    checked_at: datetime
    error: str | None = None


class TaskPageOut(BaseModel):
    items: list[dc.TaskSummary]
    total: int
    next_offset: int | None


def _raise(exc: dc.DariusError) -> HTTPException:
    """Maps adapter errors to HTTP without ever forwarding the runtime's raw body or our credentials' status."""
    detail: dict[str, Any] = {"message": exc.message, "outcome_unknown": exc.outcome_unknown}
    if exc.code:
        detail["code"] = exc.code
    if exc.task_status:
        detail["status"] = exc.task_status
    if isinstance(exc, dc.DariusNotConfigured):
        detail["code"] = "DARIUS_NOT_CONFIGURED"
        return HTTPException(503, detail)
    if isinstance(exc, dc.DariusUnavailable):
        detail["code"] = exc.code or "DARIUS_UNAVAILABLE"
        return HTTPException(502, detail)
    if isinstance(exc, dc.DariusInvalidResponse):
        detail["code"] = "DARIUS_INVALID_RESPONSE"
        return HTTPException(502, detail)
    if isinstance(exc, dc.DariusAuthError):
        # Our credential was refused: that is a configuration fault, not the browser user's 401/403.
        detail["code"] = "DARIUS_CREDENTIAL_REJECTED"
        return HTTPException(502, detail)
    if isinstance(exc, dc.DariusNotFound):
        return HTTPException(404, detail)
    if isinstance(exc, dc.DariusConflict):
        return HTTPException(409, detail)
    status = exc.status_code if exc.status_code in (400, 413, 422, 429) else 400
    return HTTPException(status, detail)


@router.get("/status", response_model=DariusStatus)
async def darius_status(client: Operator) -> DariusStatus:
    s = get_settings()
    now = datetime.now(timezone.utc)
    base = DariusStatus(
        configured=client.configured,
        reachable=False,
        circuit=client.breaker.state,
        base_url=s.darius_base_url,
        service_credential_configured=bool(s.darius_api_token),
        operator_credential_configured=bool(s.darius_operator_token),
        checked_at=now,
    )
    if not client.configured:
        base.error = "DARIUS_NOT_CONFIGURED"
        return base
    started = time.perf_counter()
    try:
        await client.health()
    except dc.DariusError as exc:
        base.circuit = client.breaker.state
        base.error = exc.code or type(exc).__name__
        return base
    base.reachable = True
    base.latency_ms = round((time.perf_counter() - started) * 1000, 1)
    base.circuit = client.breaker.state
    return base


@router.get("/tasks", response_model=TaskPageOut)
async def list_tasks(
    client: Operator,
    status: Annotated[TaskStatusFilter | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=dc.MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000_000)] = 0,
) -> TaskPageOut:
    try:
        page = await client.list_tasks(status=status, limit=limit, offset=offset)
    except dc.DariusError as exc:
        raise _raise(exc) from exc
    return TaskPageOut(items=page.items, total=page.total, next_offset=page.next_offset)


@router.get("/tasks/{task_id}", response_model=dc.TaskState)
async def get_task(task_id: str, client: Operator) -> dc.TaskState:
    try:
        return await client.get_task(task_id)
    except dc.DariusError as exc:
        raise _raise(exc) from exc


@router.get("/tasks/{task_id}/result", response_model=dc.TaskResult)
async def get_result(task_id: str, client: Operator) -> dc.TaskResult:
    try:
        return await client.get_result(task_id)
    except dc.DariusError as exc:
        raise _raise(exc) from exc


async def _decide(
    action: Literal["approve", "reject", "cancel"],
    task_id: str,
    db: AsyncSession,
    admin: User,
    call: Any,
    extra: dict[str, Any] | None = None,
) -> dc.DecisionAck:
    """Relays the decision once, then audits the outcome (success or failure) with the admin user."""
    payload: dict[str, Any] = {
        "action": action,
        "task_id": task_id,
        "admin_user_id": admin.id,
        "darius_client": "operator",
        **(extra or {}),
    }
    try:
        ack: dc.DecisionAck = await call()
    except dc.DariusError as exc:
        payload.update(
            outcome="error",
            code=exc.code or type(exc).__name__,
            http_status=exc.status_code,
            outcome_unknown=exc.outcome_unknown,
        )
        await record_log(
            db,
            source="darius_decision",
            level="warning",
            message=f"{action} {task_id}: {payload['code']}",
            payload=payload,
        )
        raise _raise(exc) from exc
    payload.update(outcome="ok", darius_status=ack.status)
    await record_log(
        db, source="darius_decision", level="info", message=f"{action} {task_id}: ok", payload=payload
    )
    return ack


@router.post("/tasks/{task_id}/approve", response_model=dc.DecisionAck)
async def approve_task(task_id: str, client: Operator, db: DbSession, admin: AdminUser) -> dc.DecisionAck:
    return await _decide("approve", task_id, db, admin, lambda: client.approve(task_id))


@router.post("/tasks/{task_id}/reject", response_model=dc.DecisionAck)
async def reject_task(
    task_id: str, body: RejectBody, client: Operator, db: DbSession, admin: AdminUser
) -> dc.DecisionAck:
    return await _decide(
        "reject", task_id, db, admin, lambda: client.reject(task_id, body.reason),
        extra={"reason": body.reason} if body.reason else None,
    )


@router.post("/tasks/{task_id}/cancel", response_model=dc.DecisionAck)
async def cancel_task(task_id: str, client: Operator, db: DbSession, admin: AdminUser) -> dc.DecisionAck:
    return await _decide("cancel", task_id, db, admin, lambda: client.cancel(task_id))
