"""Read-only admin visibility into financial_jobs — deliberately separate
from jobs/router.py: this router only ever queries FinancialJobRepository
(its own table), never JobRepository/the WhatsApp jobs table. No write
endpoints: enabling sends, cancelling, or retrying stays a `.env` +
restart operation on the financial-worker process, not an API call.
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from auth.permissions import require_admin
from database.session import get_db
from investments.models import FinancialJobStatus
from investments.repository import FinancialJobRepository

router = APIRouter(prefix="/investments/jobs", tags=["investments"], dependencies=[Depends(require_admin)])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class FinancialJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    payload: dict
    status: FinancialJobStatus
    attempts: int
    max_attempts: int
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    last_error: str | None
    result: dict | None
    created_at: datetime


@router.get("", response_model=list[FinancialJobRead])
async def list_financial_jobs(
    db: DbSession,
    job_status: Annotated[FinancialJobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    filters = {"status": job_status} if job_status is not None else {}
    return await FinancialJobRepository(db).list(limit=limit, **filters)
