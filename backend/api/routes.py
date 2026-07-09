"""All resource routers, assembled from the CRUD factory plus custom endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import api.schemas as schemas
from api.crud import create_crud_router
from auth.dependencies import CurrentUser
from auth.permissions import require_admin
from database.session import get_db
from services.cache import cache_service
from models import (
    CalendarEvent,
    ChurchMember,
    Contact,
    LogEntry,
    Message,
    Note,
    StoreCustomer,
    Task,
    TaskStatus,
)

DbSession = Annotated[AsyncSession, Depends(get_db)]

contacts_router = create_crud_router(
    model=Contact,
    prefix="/contacts",
    tag="contacts",
    create_schema=schemas.ContactCreate,
    update_schema=schemas.ContactUpdate,
    read_schema=schemas.ContactRead,
)

tasks_router = create_crud_router(
    model=Task,
    prefix="/tasks",
    tag="tasks",
    create_schema=schemas.TaskCreate,
    update_schema=schemas.TaskUpdate,
    read_schema=schemas.TaskRead,
    user_scoped=True,
)

calendar_router = create_crud_router(
    model=CalendarEvent,
    prefix="/calendar",
    tag="calendar",
    create_schema=schemas.CalendarEventCreate,
    update_schema=schemas.CalendarEventUpdate,
    read_schema=schemas.CalendarEventRead,
    user_scoped=True,
)

notes_router = create_crud_router(
    model=Note,
    prefix="/notes",
    tag="notes",
    create_schema=schemas.NoteCreate,
    update_schema=schemas.NoteUpdate,
    read_schema=schemas.NoteRead,
    user_scoped=True,
)

church_router = create_crud_router(
    model=ChurchMember,
    prefix="/church/members",
    tag="church",
    create_schema=schemas.ChurchMemberCreate,
    update_schema=schemas.ChurchMemberUpdate,
    read_schema=schemas.ChurchMemberRead,
)

store_router = create_crud_router(
    model=StoreCustomer,
    prefix="/store/customers",
    tag="store",
    create_schema=schemas.StoreCustomerCreate,
    update_schema=schemas.StoreCustomerUpdate,
    read_schema=schemas.StoreCustomerRead,
)


# --- Messages (read-only) -------------------------------------------------
messages_router = APIRouter(prefix="/messages", tags=["messages"])


@messages_router.get("", response_model=list[schemas.MessageRead])
async def list_messages(
    db: DbSession,
    _: CurrentUser,
    contact_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Message]:
    statement = select(Message).order_by(Message.id.desc()).limit(limit).offset(offset)
    if contact_id is not None:
        statement = statement.where(Message.contact_id == contact_id)
    return list((await db.execute(statement)).scalars().all())


# --- Logs (read-only, admin) ------------------------------------------------
logs_router = APIRouter(
    prefix="/logs", tags=["logs"], dependencies=[Depends(require_admin)]
)


@logs_router.get("", response_model=list[schemas.LogRead])
async def list_logs(
    db: DbSession,
    _: CurrentUser,
    source: str | None = None,
    level: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[LogEntry]:
    statement = select(LogEntry).order_by(LogEntry.id.desc()).limit(limit).offset(offset)
    if source is not None:
        statement = statement.where(LogEntry.source == source)
    if level is not None:
        statement = statement.where(LogEntry.level == level)
    return list((await db.execute(statement)).scalars().all())


# --- Dashboard ------------------------------------------------------------
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@dashboard_router.get("/summary")
async def dashboard_summary(db: DbSession, current_user: CurrentUser) -> dict:
    cache_key = f"dashboard:summary:{current_user.id}"
    cached = await cache_service.get(cache_key)
    if cached is not None:
        return cached

    async def count(statement) -> int:
        return (await db.execute(statement)).scalar_one()

    summary = {
        "contacts": await count(select(func.count()).select_from(Contact)),
        "messages": await count(select(func.count()).select_from(Message)),
        "pending_tasks": await count(
            select(func.count())
            .select_from(Task)
            .where(Task.user_id == current_user.id, Task.status == TaskStatus.PENDING)
        ),
        "notes": await count(
            select(func.count()).select_from(Note).where(Note.user_id == current_user.id)
        ),
        "events": await count(
            select(func.count())
            .select_from(CalendarEvent)
            .where(CalendarEvent.user_id == current_user.id)
        ),
        "church_members": await count(select(func.count()).select_from(ChurchMember)),
        "store_customers": await count(select(func.count()).select_from(StoreCustomer)),
    }
    await cache_service.set(cache_key, summary, ttl_seconds=30)
    return summary
