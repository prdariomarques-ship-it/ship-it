"""Admin Dashboard API — read-only (P4) and job management operations (P6).

Read-only endpoints (P4) query existing data: Agent/Tool Registry, existing
tables (`users`, `jobs`, `logs`, etc.), Prometheus registry, and existing
services. Job management endpoints (P6) allow admins to cancel and retry jobs
with atomic state transitions, audit logging, and event bus integration.
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin import schemas, service
from auth.permissions import require_admin
from database.session import get_db
from events.bus import event_bus
from models.email_account import EmailAccount
from models.gcalendar_account import GoogleCalendarAccount
from models.gcontacts_account import GoogleContactsAccount
from models.gdrive_account import GoogleDriveAccount
from models.job import Job, JobStatus
from models.log import LogEntry
from models.message import Message, MessageDirection
from models.user import User
from services.audit import record_log
from services.cache import cache_service
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

DbSession = Annotated[AsyncSession, Depends(get_db)]

_PERIOD_TO_TIMEDELTA = {
    "today": timedelta(hours=24),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


@router.get("", response_model=schemas.AdminIndex)
async def admin_index(db: DbSession) -> schemas.AdminIndex:
    from agents.registry import list_agents
    from agents.tools.registry import list_tools

    cache_key = "admin:index"
    cached = await cache_service.get(cache_key)
    if cached is not None:
        return schemas.AdminIndex(**cached)

    users_total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    google_connected = 0
    for model in (EmailAccount, GoogleCalendarAccount, GoogleContactsAccount, GoogleDriveAccount):
        google_connected += (await db.execute(select(func.count()).select_from(model))).scalar_one()

    whatsapp_status = await service.check_whatsapp()

    result = schemas.AdminIndex(
        users_total=users_total,
        agents_total=len(list_agents()),
        tools_total=len(list_tools()),
        google_connected_accounts=google_connected,
        whatsapp_connected=whatsapp_status.online,
        uptime_seconds=service.uptime_seconds(),
    )
    await cache_service.set(cache_key, result.model_dump(), ttl_seconds=15)
    return result


@router.get("/status", response_model=list[schemas.ComponentStatus])
async def admin_status(db: DbSession) -> list[schemas.ComponentStatus]:
    heartbeat = datetime.now(timezone.utc)
    backend = schemas.ComponentStatus(
        name="backend", online=True, detail="", latency_ms=0.0, last_heartbeat=heartbeat
    )
    checks = [
        await service.check_database(db),
        await service.check_redis(),
        await service.check_qdrant(),
        await service.check_whatsapp(),
        service.check_event_bus(),
    ]
    for check in checks:
        check.last_heartbeat = heartbeat

    # "Memory" mirrors the Qdrant probe: the Memory Manager facade has no
    # independent health signal of its own — it degrades exactly when Qdrant
    # does (see memory/manager.py). Reported as a separate card per the
    # spec, but never a fabricated distinct signal.
    qdrant_check = next(c for c in checks if c.name == "qdrant")
    memory_check = schemas.ComponentStatus(
        name="memory",
        online=qdrant_check.online,
        detail="mirrors qdrant (Memory Manager has no independent probe)",
        latency_ms=qdrant_check.latency_ms,
        last_heartbeat=heartbeat,
    )

    # Google OAuth: "online" here means the app has the client credentials
    # configured to run the OAuth flow at all, not that a specific user's
    # token is currently valid (that's per-account, shown in /admin/google).
    settings = get_settings()
    google_configured = bool(settings.google_client_id and settings.google_client_secret)
    google_check = schemas.ComponentStatus(
        name="google_oauth",
        online=google_configured,
        detail="client credentials configured" if google_configured else "GOOGLE_CLIENT_ID/SECRET not set",
        latency_ms=None,
        last_heartbeat=heartbeat,
    )

    return [backend, *checks, memory_check, google_check]


@router.get("/system", response_model=schemas.SystemInfo)
async def admin_system() -> schemas.SystemInfo:
    settings = get_settings()
    git = service.git_info()
    resources = service.system_resources()
    pool = service.db_pool_info()
    return schemas.SystemInfo(
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        commit=git["commit"],
        branch=git["branch"],
        tag=git["tag"],
        uptime_seconds=service.uptime_seconds(),
        llm_provider=settings.llm_provider,
        embedding_provider=settings.embedding_provider,
        whatsapp_provider=settings.whatsapp_provider,
        mail_provider=settings.mail_provider,
        calendar_provider=settings.calendar_provider,
        contacts_provider=settings.contacts_provider,
        drive_provider=settings.drive_provider,
        auto_reply_enabled=settings.auto_reply_enabled,
        jobs_enabled=settings.jobs_enabled,
        **resources,
        **pool,
    )


@router.get("/agents", response_model=list[schemas.AgentAdminInfo])
async def admin_agents(db: DbSession) -> list[schemas.AgentAdminInfo]:
    from agents.registry import list_agents

    snapshot = service.prometheus_snapshot()
    results = []
    for agent in list_agents():
        stats = service.agent_run_stats(snapshot, agent.name)
        last_log = await service.recent_log_for_source(db, f"agent:{agent.name}")
        results.append(
            schemas.AgentAdminInfo(
                name=agent.name,
                description=agent.description,
                tool_count=len(agent.tools),
                last_execution=last_log.created_at if last_log else None,
                **stats,
            )
        )
    return results


def _infer_tool_category(tool) -> str:
    """Best-effort grouping from the tool handler's own module path (e.g.
    `agents.tools.gcalendar_tools` -> "gcalendar") — real code structure,
    not an invented taxonomy. Falls back to "geral" for module names that
    don't follow the `*_tools` convention."""
    module = getattr(tool.handler, "__module__", "") or ""
    leaf = module.rsplit(".", 1)[-1]
    return leaf.removesuffix("_tools") or "geral"


@router.get("/tools", response_model=list[schemas.ToolAdminInfo])
async def admin_tools() -> list[schemas.ToolAdminInfo]:
    from agents.registry import list_agents
    from agents.tools.registry import list_tools

    tool_to_agents: dict[str, list[str]] = {}
    for agent in list_agents():
        for tool in agent.tools:
            tool_to_agents.setdefault(tool.name, []).append(agent.name)

    snapshot = service.prometheus_snapshot()
    results = []
    for tool in list_tools():
        stats = service.tool_call_stats(snapshot, tool.name)
        results.append(
            schemas.ToolAdminInfo(
                name=tool.name,
                description=tool.description,
                category=_infer_tool_category(tool),
                agents=tool_to_agents.get(tool.name, []),
                parameters=tool.parameters,
                permissions=None,  # not modeled on Tool — see docs/DASHBOARD.md
                last_call=None,  # no per-tool timestamped record exists — see docs/DASHBOARD.md
                **stats,
            )
        )
    return results


@router.get("/logs")
async def admin_logs(
    db: DbSession,
    source: str | None = None,
    level: str | None = None,
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    statement = select(LogEntry).order_by(LogEntry.id.desc()).limit(limit).offset(offset)
    if source:
        statement = statement.where(LogEntry.source == source)
    if level:
        statement = statement.where(LogEntry.level == level)
    if search:
        statement = statement.where(LogEntry.message.ilike(f"%{search}%"))
    rows = (await db.execute(statement)).scalars().all()
    return [
        {
            "id": row.id,
            "level": row.level,
            "source": row.source,
            "message": row.message,
            "payload": row.payload,
            "created_at": row.created_at,
        }
        for row in rows
    ]


async def _domain_status(db: DbSession, model, domain: str) -> schemas.GoogleDomainStatus:
    statement = select(model)
    rows = (await db.execute(statement)).scalars().all()
    accounts = [
        schemas.GoogleAccountInfo(
            user_id=row.user_id,
            label=getattr(row, "account_label", None) or getattr(row, "email_address", ""),
            scopes=row.scopes,
            connected_at=row.connected_at,
        )
        for row in rows
    ]
    return schemas.GoogleDomainStatus(domain=domain, connected_accounts=len(accounts), accounts=accounts)


@router.get("/google", response_model=schemas.GoogleWorkspaceStatus)
async def admin_google(db: DbSession) -> schemas.GoogleWorkspaceStatus:
    mail = await _domain_status(db, EmailAccount, "mail")
    calendar = await _domain_status(db, GoogleCalendarAccount, "calendar")
    contacts = await _domain_status(db, GoogleContactsAccount, "contacts")
    drive = await _domain_status(db, GoogleDriveAccount, "drive")

    indexed_count, last_indexed = await service.drive_index_stats(db)
    drive.indexed_items = indexed_count
    drive.last_indexed_at = last_indexed

    return schemas.GoogleWorkspaceStatus(mail=mail, calendar=calendar, contacts=contacts, drive=drive)


@router.get("/memory", response_model=schemas.MemoryStats)
async def admin_memory(db: DbSession) -> schemas.MemoryStats:
    from memory.service import memory_service

    settings = get_settings()
    collection_stats = schemas.MemoryCollectionStats(
        name=settings.qdrant_collection, points_count=None, vectors_count=None, status=None
    )
    try:
        info = await memory_service.client.get_collection(settings.qdrant_collection)
        collection_stats = schemas.MemoryCollectionStats(
            name=settings.qdrant_collection,
            points_count=info.points_count,
            vectors_count=info.vectors_count,
            status=info.status.value if info.status is not None else None,
        )
    except Exception:  # noqa: BLE001 - collection may not exist yet on a fresh install
        pass

    by_source = await service.embeddings_by_source(db)
    total = sum(by_source.values())
    drive_count, drive_last_indexed = await service.drive_index_stats(db)

    return schemas.MemoryStats(
        collection=collection_stats,
        embeddings_total=total,
        embeddings_by_source=by_source,
        drive_indexed_files=drive_count,
        drive_last_indexed_at=drive_last_indexed,
        cache_backend="redis" if cache_service._redis_available else "in-memory (fallback)",
    )


@router.get("/executions", response_model=list[schemas.ExecutionEntry])
async def admin_executions(
    db: DbSession,
    period: Annotated[str, Query(pattern="^(today|24h|7d|30d)$")] = "24h",
    agent: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[schemas.ExecutionEntry]:
    """Best-effort execution timeline built from two existing sources —
    `jobs` (background work) and `logs` (agent/whatsapp events) — there is
    no dedicated per-agent/per-tool execution-audit table (see
    docs/DASHBOARD.md). Filtering by Tool is not offered because no record
    ties a log/job row to a specific tool call."""
    since = datetime.now(timezone.utc) - _PERIOD_TO_TIMEDELTA[period]

    job_statement = select(Job).where(Job.created_at >= since).order_by(Job.id.desc()).limit(limit)
    if agent:
        job_statement = job_statement.where(Job.name.ilike(f"%{agent}%"))
    jobs = (await db.execute(job_statement)).scalars().all()

    log_statement = (
        select(LogEntry)
        .where(LogEntry.created_at >= since, LogEntry.source.like("agent:%"))
        .order_by(LogEntry.id.desc())
        .limit(limit)
    )
    if agent:
        log_statement = log_statement.where(LogEntry.source == f"agent:{agent}")
    logs = (await db.execute(log_statement)).scalars().all()

    entries: list[schemas.ExecutionEntry] = []
    for job in jobs:
        duration = None
        if job.started_at and job.finished_at:
            duration = (job.finished_at - job.started_at).total_seconds()
        entries.append(
            schemas.ExecutionEntry(
                kind="job",
                id=job.id,
                timestamp=job.created_at,
                name=job.name,
                agent=None,
                status=job.status.value,
                detail=job.last_error or "",
                duration_seconds=duration,
            )
        )
    for log in logs:
        entries.append(
            schemas.ExecutionEntry(
                kind="log",
                id=log.id,
                timestamp=log.created_at,
                name=log.source,
                agent=log.source.removeprefix("agent:"),
                status=log.level,
                detail=log.message,
                duration_seconds=None,
            )
        )

    entries.sort(key=lambda entry: entry.timestamp, reverse=True)
    return entries[:limit]


@router.get("/users", response_model=list[schemas.UserAdminRead])
async def admin_users(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    statement = select(User).order_by(User.id.asc()).limit(limit).offset(offset)
    rows = (await db.execute(statement)).scalars().all()
    return [
        schemas.UserAdminRead(
            id=row.id, email=row.email, full_name=row.full_name, role=row.role.value,
            is_active=row.is_active, created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/metrics")
async def admin_metrics() -> dict:
    """Raw Prometheus counter/histogram snapshot, timestamped. These are
    cumulative totals (Prometheus semantics), not per-minute rates — the
    frontend derives a rate by polling this endpoint and diffing successive
    snapshots (see docs/DASHBOARD.md)."""
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "metrics": service.prometheus_snapshot()}


@router.get("/whatsapp", response_model=schemas.WhatsAppStatus)
async def admin_whatsapp(db: DbSession) -> schemas.WhatsAppStatus:
    from providers.whatsapp.factory import get_whatsapp_provider

    status_check = await service.check_whatsapp()
    provider = get_whatsapp_provider()

    queue_depth = (
        await db.execute(
            select(func.count()).select_from(Job).where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
        )
    ).scalar_one()
    sent = (
        await db.execute(
            select(func.count()).select_from(Message).where(Message.direction == MessageDirection.OUTBOUND)
        )
    ).scalar_one()
    received = (
        await db.execute(
            select(func.count()).select_from(Message).where(Message.direction == MessageDirection.INBOUND)
        )
    ).scalar_one()

    return schemas.WhatsAppStatus(
        provider=provider.name,
        connected=status_check.online,
        detail=status_check.detail,
        queue_depth=queue_depth,
        messages_sent=sent,
        messages_received=received,
    )


# --- P6: Job Management Operations (ADMIN-only, state-changing) ---


@router.post("/jobs/{job_id}/cancel", summary="Cancel a queued or running job", tags=["admin", "jobs"])
async def admin_cancel_job(
    job_id: int,
    db: DbSession,
) -> dict:
    """Atomically cancel a QUEUED or RUNNING job. Cannot cancel already succeeded/failed/cancelled jobs."""
    from sqlalchemy import update

    # SELECT FOR UPDATE: acquire exclusive row lock before checking/updating state
    stmt = select(Job).where(Job.id == job_id).with_for_update()
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Validate state: only QUEUED and RUNNING can be cancelled
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in {job.status.value} state; only QUEUED or RUNNING jobs can be cancelled",
        )

    # Update state within same transaction (atomic with lock acquired above)
    now = datetime.now(timezone.utc)
    await db.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status=JobStatus.CANCELLED, finished_at=now)
    )
    await db.commit()

    # Audit logging (includes trace_id via RequestIDFilter)
    logger.info(
        "Admin cancelled job",
        extra={"context": {"job_id": job_id, "previous_status": job.status.value, "new_status": "cancelled"}},
    )

    # Persist to audit trail
    await record_log(
        db,
        source="admin:job_cancel",
        message=f"Job {job_id} cancelled by admin",
        level="info",
        payload={"job_id": job_id, "job_name": job.name, "previous_status": job.status.value},
    )

    # Emit event (EventBus listener notifies UI dashboards, notification services)
    await event_bus.publish(
        "admin.job_cancelled",
        {
            "job_id": job_id,
            "job_name": job.name,
            "previous_status": job.status.value,
            "cancelled_at": now.isoformat(),
        },
    )

    return {"job_id": job_id, "status": JobStatus.CANCELLED.value, "finished_at": now.isoformat()}


@router.post("/jobs/{job_id}/retry", summary="Retry a failed or cancelled job", tags=["admin", "jobs"])
async def admin_retry_job(
    job_id: int,
    db: DbSession,
) -> dict:
    """Atomically reset a FAILED or CANCELLED job to QUEUED for re-execution. Clears error state."""
    from sqlalchemy import update

    # SELECT FOR UPDATE: acquire exclusive row lock before checking/updating state
    stmt = select(Job).where(Job.id == job_id).with_for_update()
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Validate state: only FAILED and CANCELLED can be retried
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry job in {job.status.value} state; only FAILED or CANCELLED jobs can be retried",
        )

    # Update state within same transaction (atomic with lock acquired above)
    now = datetime.now(timezone.utc)
    await db.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(
            status=JobStatus.QUEUED,
            attempts=0,  # Reset retry count
            last_error=None,  # Clear previous error
            scheduled_at=now,  # Immediate re-queue
        )
    )
    await db.commit()

    # Audit logging (includes trace_id via RequestIDFilter)
    logger.info(
        "Admin retried job",
        extra={"context": {"job_id": job_id, "previous_status": job.status.value, "new_status": "queued"}},
    )

    # Persist to audit trail
    await record_log(
        db,
        source="admin:job_retry",
        message=f"Job {job_id} retried by admin (attempts reset to 0)",
        level="info",
        payload={"job_id": job_id, "job_name": job.name, "previous_status": job.status.value},
    )

    # Emit event (EventBus listener notifies UI dashboards, notification services)
    await event_bus.publish(
        "admin.job_retried",
        {
            "job_id": job_id,
            "job_name": job.name,
            "previous_status": job.status.value,
            "retried_at": now.isoformat(),
            "attempts_reset_to": 0,
        },
    )

    return {"job_id": job_id, "status": JobStatus.QUEUED.value, "scheduled_at": now.isoformat()}
