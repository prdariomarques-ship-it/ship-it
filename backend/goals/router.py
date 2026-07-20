"""Goal management endpoints: CRUD, status transitions, dependencies,
approval workflow, progress tracking and execution history."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import CurrentUser
from auth.permissions import require_admin
from database.session import get_db
from goals.service import ApprovalRequiredError, CyclicDependencyError, GoalService
from models.goal import Goal, GoalPriority, GoalStatus
from models.log import LogEntry
from repositories.goal import GoalRepository

router = APIRouter(prefix="/goals", tags=["goals"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class GoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    description: str | None
    status: GoalStatus
    priority: GoalPriority
    deadline: datetime | None
    progress_percent: int
    requires_approval: bool
    approved_at: datetime | None
    approved_by_id: int | None
    recurrence_interval_days: int | None
    recurrence_parent_id: int | None
    created_at: datetime
    updated_at: datetime


class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    priority: GoalPriority = GoalPriority.MEDIUM
    deadline: datetime | None = None
    recurrence_interval_days: int | None = Field(default=None, ge=1)
    requires_approval: bool = False


class GoalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    priority: GoalPriority | None = None
    deadline: datetime | None = None


class GoalStatusUpdate(BaseModel):
    status: GoalStatus


class GoalProgressUpdate(BaseModel):
    progress_percent: int = Field(ge=0, le=100)


class GoalDependencyCreate(BaseModel):
    depends_on_id: int


class GoalHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str
    message: str
    payload: dict
    created_at: datetime


async def _get_owned_goal_or_404(
    repository: GoalRepository, goal_id: int, user_id: int
) -> Goal:
    goal = await repository.get(goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found"
        )
    return goal


@router.get("", response_model=list[GoalRead])
async def list_goals(
    db: DbSession,
    current_user: CurrentUser,
    goal_status: Annotated[GoalStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Goal]:
    repository = GoalRepository(db)
    filters = {"status": goal_status} if goal_status is not None else {}
    return await repository.list(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        **filters,  # type: ignore[arg-type]
    )


@router.get("/ready", response_model=list[GoalRead])
async def list_ready_goals(
    db: DbSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Goal]:
    """PENDING goals with no incomplete dependency, ranked by priority_score."""
    return await GoalService(db).ready_goals(current_user.id, limit=limit)


@router.post("", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: GoalCreate, db: DbSession, current_user: CurrentUser
) -> Goal:
    return await GoalService(db).create_goal(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        deadline=payload.deadline,
        recurrence_interval_days=payload.recurrence_interval_days,
        requires_approval=payload.requires_approval,
    )


@router.get("/{goal_id}", response_model=GoalRead)
async def get_goal(goal_id: int, db: DbSession, current_user: CurrentUser) -> Goal:
    return await _get_owned_goal_or_404(GoalRepository(db), goal_id, current_user.id)


@router.get("/{goal_id}/history", response_model=list[GoalHistoryEntry])
async def get_goal_history(
    goal_id: int,
    db: DbSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[LogEntry]:
    """Execution history: every recorded transition for this goal, newest
    first. Owner-scoped view over the same `logs` table `/api/logs` (admin
    only) already exposes -- reuses the existing audit trail rather than a
    new one."""
    await _get_owned_goal_or_404(GoalRepository(db), goal_id, current_user.id)
    statement = (
        select(LogEntry)
        .where(LogEntry.source == f"goal:{goal_id}")
        .order_by(LogEntry.id.desc())
        .limit(limit)
    )
    return list((await db.execute(statement)).scalars().all())


@router.post(
    "/{goal_id}/approve", response_model=GoalRead, dependencies=[Depends(require_admin)]
)
async def approve_goal(goal_id: int, db: DbSession, current_user: CurrentUser) -> Goal:
    """Human approval gate. Admin-only by design -- the goal's own owner is
    not automatically trusted to self-approve a goal that was explicitly
    flagged as requiring approval."""
    repository = GoalRepository(db)
    goal = await repository.get(goal_id)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found"
        )
    try:
        return await GoalService(db).approve_goal(goal, approved_by_id=current_user.id)
    except ApprovalRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.patch("/{goal_id}", response_model=GoalRead)
async def update_goal(
    goal_id: int, payload: GoalUpdate, db: DbSession, current_user: CurrentUser
) -> Goal:
    """Edit title/description/priority/deadline. Unlike `/status`, not gated
    by the approval workflow -- only fields actually sent in the request
    body are touched (`exclude_unset`), so a nullable field like `deadline`
    can be explicitly cleared without also resetting the others."""
    repository = GoalRepository(db)
    goal = await _get_owned_goal_or_404(repository, goal_id, current_user.id)
    fields = payload.model_dump(exclude_unset=True)
    return await GoalService(db).update_details(goal, **fields)


@router.patch("/{goal_id}/status", response_model=GoalRead)
async def update_goal_status(
    goal_id: int, payload: GoalStatusUpdate, db: DbSession, current_user: CurrentUser
) -> Goal:
    repository = GoalRepository(db)
    goal = await _get_owned_goal_or_404(repository, goal_id, current_user.id)
    try:
        return await GoalService(db).update_status(goal, payload.status)
    except ApprovalRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.patch("/{goal_id}/progress", response_model=GoalRead)
async def update_goal_progress(
    goal_id: int, payload: GoalProgressUpdate, db: DbSession, current_user: CurrentUser
) -> Goal:
    repository = GoalRepository(db)
    goal = await _get_owned_goal_or_404(repository, goal_id, current_user.id)
    return await GoalService(db).update_progress(goal, payload.progress_percent)


@router.get("/{goal_id}/dependencies", response_model=list[GoalRead])
async def list_dependencies(
    goal_id: int, db: DbSession, current_user: CurrentUser
) -> list[Goal]:
    """Full goal rows this goal depends on (not just ids), so the caller can
    show a title/status instead of a bare id."""
    repository = GoalRepository(db)
    await _get_owned_goal_or_404(repository, goal_id, current_user.id)
    return await repository.dependencies(goal_id)


@router.post("/{goal_id}/dependencies", status_code=status.HTTP_201_CREATED)
async def add_dependency(
    goal_id: int,
    payload: GoalDependencyCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    repository = GoalRepository(db)
    await _get_owned_goal_or_404(repository, goal_id, current_user.id)
    await _get_owned_goal_or_404(repository, payload.depends_on_id, current_user.id)
    try:
        await GoalService(db).add_dependency(goal_id, payload.depends_on_id)
    except CyclicDependencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return {"goal_id": goal_id, "depends_on_id": payload.depends_on_id}


@router.delete(
    "/{goal_id}/dependencies/{depends_on_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_dependency(
    goal_id: int, depends_on_id: int, db: DbSession, current_user: CurrentUser
) -> None:
    repository = GoalRepository(db)
    await _get_owned_goal_or_404(repository, goal_id, current_user.id)
    removed = await repository.remove_dependency(goal_id, depends_on_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dependency not found"
        )
