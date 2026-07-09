"""Job queue management endpoints (admin only)."""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.permissions import require_admin
from database.session import get_db
from jobs.registry import UnknownJobError, registered_jobs, resolve_handler
from jobs.service import JobService
from models.job import Job, JobStatus
from repositories.job import JobRepository

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_admin)])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    payload: dict
    status: JobStatus
    attempts: int
    max_attempts: int
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    last_error: str | None
    created_at: datetime


class JobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    payload: dict = {}
    delay_seconds: float = Field(default=0, ge=0)
    max_attempts: int | None = Field(default=None, ge=1, le=10)


@router.get("/handlers")
async def list_handlers() -> dict:
    return {"handlers": registered_jobs()}


@router.get("", response_model=list[JobRead])
async def list_jobs(
    db: DbSession,
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Job]:
    repository = JobRepository(db)
    filters = {"status": job_status} if job_status is not None else {}
    return await repository.list(limit=limit, offset=offset, **filters)


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def enqueue_job(payload: JobCreate, db: DbSession) -> Job:
    try:
        resolve_handler(payload.name)
    except UnknownJobError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return await JobService(db).enqueue(
        payload.name,
        payload.payload,
        delay_seconds=payload.delay_seconds,
        max_attempts=payload.max_attempts,
    )


@router.post("/{job_id}/cancel", response_model=JobRead)
async def cancel_job(job_id: int, db: DbSession) -> Job:
    repository = JobRepository(db)
    job = await repository.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Job is already {job.status.value}"
        )
    return await repository.update(job, status=JobStatus.CANCELLED)
