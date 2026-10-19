"""Admin control of the automation kill switch (global and per WhatsApp instance).

The switch itself is enforced in the backend send path
(`services/automation_suspension.py` + `jobs/handlers.py::send_whatsapp_text`);
this router only changes and reports it. Every change needs a reason and is
audited with the admin user.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.permissions import require_admin
from database.session import get_db
from models.user import User
from services import automation_suspension as suspension
from utils.config import get_settings

router = APIRouter(
    prefix="/admin/automation", tags=["admin"], dependencies=[Depends(require_admin)]
)

DbSession = Annotated[AsyncSession, Depends(get_db)]
AdminUser = Annotated[User, Depends(require_admin)]


class SuspensionState(BaseModel):
    global_suspended: bool
    suspended_instances: list[str]


class SuspensionChange(BaseModel):
    suspended: bool
    reason: str = Field(min_length=suspension.MIN_REASON_CHARS, max_length=suspension.MAX_REASON_CHARS)


@router.get("/suspension", response_model=SuspensionState)
async def get_suspension() -> SuspensionState:
    return SuspensionState(**suspension.state(get_settings()))


@router.put("/suspension/global", response_model=SuspensionState)
async def put_global_suspension(body: SuspensionChange, db: DbSession, admin: AdminUser) -> SuspensionState:
    try:
        return SuspensionState(**await suspension.set_global(db, body.suspended, admin.id, body.reason))
    except suspension.InvalidSuspensionRequest as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/suspension/instances/{instance}", response_model=SuspensionState)
async def put_instance_suspension(
    instance: Annotated[str, Path(max_length=64)],
    body: SuspensionChange,
    db: DbSession,
    admin: AdminUser,
) -> SuspensionState:
    try:
        return SuspensionState(
            **await suspension.set_instance(db, instance, body.suspended, admin.id, body.reason)
        )
    except suspension.InvalidSuspensionRequest as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
