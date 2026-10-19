"""Admin control of the automation kill switch (global and per WhatsApp instance).

The switch itself is enforced in the backend send path
(`services/automation_suspension.py` + `jobs/handlers.py::send_whatsapp_text`);
this router only changes and reports it. Every change needs a reason and is
audited with the admin user. Status codes: 422 invalid input, 404 instance not
configured (suspending only), 200 otherwise -- `changed=false` on a repeated edit.
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


class SuspensionDetail(BaseModel):
    scope: str
    reason: str
    actor_id: int | None
    since: str | None


class SuspensionState(BaseModel):
    global_suspended: bool
    global_forced_by_environment: bool
    suspended_instances: list[str]
    configured_instances: list[str]
    details: list[SuspensionDetail]
    changed: bool | None = None


class SuspensionChange(BaseModel):
    suspended: bool
    reason: str = Field(min_length=suspension.MIN_REASON_CHARS, max_length=suspension.MAX_REASON_CHARS)


def _result(change: suspension.Change) -> SuspensionState:
    return SuspensionState(**change.state, changed=change.changed)


@router.get("/suspension", response_model=SuspensionState)
async def get_suspension(db: DbSession) -> SuspensionState:
    return SuspensionState(**await suspension.state(db, get_settings()))


@router.put("/suspension/global", response_model=SuspensionState)
async def put_global_suspension(body: SuspensionChange, db: DbSession, admin: AdminUser) -> SuspensionState:
    try:
        return _result(await suspension.set_global(db, get_settings(), body.suspended, admin.id, body.reason))
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
        return _result(
            await suspension.set_instance(db, get_settings(), instance, body.suspended, admin.id, body.reason)
        )
    except suspension.InvalidSuspensionRequest as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except suspension.UnknownInstance as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
