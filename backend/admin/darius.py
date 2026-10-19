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
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth.permissions import require_admin
from database.session import get_db
from models.automation_suspension import SCOPE_GLOBAL, instance_scope
from models.user import User
from repositories.darius_whatsapp_task import DariusWhatsAppTaskRepository
from services import automation_suspension, darius_whatsapp
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


@router.get("/metrics", response_model=dc.RuntimeMetrics)
async def runtime_metrics(client: Operator) -> dc.RuntimeMetrics:
    """Relays the runtime's own operator metrics. Nothing is computed or defaulted here."""
    try:
        return await client.get_runtime_metrics()
    except dc.DariusError as exc:
        raise _raise(exc) from exc


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


# --- WhatsApp -> DARIUS links (read-only; the audit trail lives in darius_whatsapp_tasks) -----------------------

WhatsAppLinkStatus = Literal["submitting", "submitted", "reply_queued", "failed", "cancelled", "expired", "skipped"]



def _as_utc(value: datetime | None) -> datetime | None:
    """Stored timestamps are UTC. A driver that does not type the column (SQLite) hands back a naive value, which the
    browser would read as local time (3 h off in Brasilia); PostgreSQL already returns it aware."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

class WhatsAppLinkOut(BaseModel):
    """One inbound message -> one DARIUS task. Carries ids, sizes and states only: never message or reply text."""

    id: int
    instance: str
    status: str
    darius_task_id: str | None
    darius_status: str | None
    message_id: int
    contact_id: int
    attempts: int
    last_error: str | None
    reply_chars: int | None
    history: list[dict[str, Any]]
    created_at: datetime
    finished_at: datetime | None

    @field_validator("created_at", "finished_at")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class WhatsAppLinkPage(BaseModel):
    items: list[WhatsAppLinkOut]
    counts: dict[str, int]
    next_offset: int | None


class WhatsAppInstanceRouting(BaseModel):
    instance: str
    routed_to_darius: bool
    suspended: bool
    suspension_reason: str | None = None


class WhatsAppRouting(BaseModel):
    """What decides where an inbound WhatsApp message goes, straight from configuration and the suspension table."""

    enabled: bool
    darius_configured: bool
    reply_timeout_seconds: int
    global_suspended: bool
    global_suspension_reason: str | None = None
    instances: list[WhatsAppInstanceRouting]
    unknown_routed_instances: list[str]


@router.get("/whatsapp-tasks", response_model=WhatsAppLinkPage)
async def list_whatsapp_links(
    db: DbSession,
    status: Annotated[WhatsAppLinkStatus | None, Query()] = None,
    instance: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000_000)] = 0,
) -> WhatsAppLinkPage:
    repo = DariusWhatsAppTaskRepository(db)
    rows = await repo.list_recent(status=status, instance=instance, limit=limit + 1, offset=offset)
    page, more = rows[:limit], len(rows) > limit
    return WhatsAppLinkPage(
        items=[WhatsAppLinkOut.model_validate(row, from_attributes=True) for row in page],
        counts=await repo.counts_by_status(),
        next_offset=offset + limit if more else None,
    )


@router.get("/whatsapp-routing", response_model=WhatsAppRouting)
async def whatsapp_routing(db: DbSession) -> WhatsAppRouting:
    settings = get_settings()
    suspension = await automation_suspension.state(db, settings)
    reasons = {item["scope"]: item["reason"] for item in suspension["details"]}
    suspended = set(suspension["suspended_instances"])
    routed = darius_whatsapp.routed_instances(settings)
    configured = suspension["configured_instances"]
    return WhatsAppRouting(
        enabled=settings.darius_whatsapp_enabled,
        darius_configured=bool(settings.darius_base_url and settings.darius_api_token),
        reply_timeout_seconds=settings.darius_whatsapp_reply_timeout_seconds,
        global_suspended=suspension["global_suspended"],
        global_suspension_reason=reasons.get(SCOPE_GLOBAL),
        instances=[
            WhatsAppInstanceRouting(
                instance=name,
                routed_to_darius=bool(settings.darius_whatsapp_enabled and name in routed),
                suspended=name in suspended,
                suspension_reason=reasons.get(instance_scope(name)),
            )
            for name in configured
        ],
        unknown_routed_instances=sorted(routed - set(configured)),
    )


class PausedConversation(BaseModel):
    contact_id: int
    contact_name: str | None
    phone_tail: str | None  # last 4 digits only: enough to tell conversations apart, not enough to contact anyone
    instance: str
    revision: int
    paused_since: datetime | None
    reason: str | None
    actor_id: int | None
    send_in_flight: bool

    @field_validator("paused_since")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        # Raw SELECT: the driver may not type the column (see _as_utc).
        return _as_utc(value)


class PausedConversationPage(BaseModel):
    items: list[PausedConversation]
    total: int
    next_offset: int | None


_PAUSED_SELECT = """
SELECT c.contact_id AS contact_id, c.instance AS instance, c.revision AS revision, c.inflight AS inflight,
       ct.name AS contact_name, ct.phone AS phone,
       (SELECT a.created_at FROM conversation_control_audit a
         WHERE a.contact_id = c.contact_id AND a.instance = c.instance AND a.action = 'pause'
         ORDER BY a.revision DESC LIMIT 1) AS paused_since,
       (SELECT a.reason FROM conversation_control_audit a
         WHERE a.contact_id = c.contact_id AND a.instance = c.instance AND a.action = 'pause'
         ORDER BY a.revision DESC LIMIT 1) AS reason,
       (SELECT a.actor_id FROM conversation_control_audit a
         WHERE a.contact_id = c.contact_id AND a.instance = c.instance AND a.action = 'pause'
         ORDER BY a.revision DESC LIMIT 1) AS actor_id
  FROM conversation_controls c JOIN contacts ct ON ct.id = c.contact_id
 WHERE c.paused = true {instance_filter}
 ORDER BY paused_since DESC, c.contact_id, c.instance
 LIMIT :limit OFFSET :offset
"""


@router.get("/paused-conversations", response_model=PausedConversationPage)
async def paused_conversations(
    db: DbSession,
    instance: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000_000)] = 0,
) -> PausedConversationPage:
    """Conversations a human took over (`conversation_controls.paused`): automatic replies - DARIUS included -
    are blocked for them until the owner resumes. Read-only; resuming stays in the conversation controls."""
    params: dict[str, Any] = {"limit": limit + 1, "offset": offset}
    filter_sql = ""
    count_sql = "SELECT COUNT(*) FROM conversation_controls c WHERE c.paused = true"
    if instance:
        params["instance"] = instance
        filter_sql = "AND c.instance = :instance"
        count_sql += " AND c.instance = :instance"
    total = int((await db.execute(text(count_sql), params)).scalar_one())
    rows = (await db.execute(text(_PAUSED_SELECT.format(instance_filter=filter_sql)), params)).mappings().all()
    page, more = rows[:limit], len(rows) > limit
    return PausedConversationPage(
        items=[
            PausedConversation(
                contact_id=r["contact_id"], contact_name=r["contact_name"],
                phone_tail=(r["phone"] or "")[-4:] or None, instance=r["instance"], revision=int(r["revision"]),
                paused_since=r["paused_since"], reason=r["reason"], actor_id=r["actor_id"],
                send_in_flight=r["inflight"] is not None,
            )
            for r in page
        ],
        total=total,
        next_offset=offset + limit if more else None,
    )
