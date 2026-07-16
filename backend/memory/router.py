from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import CurrentUser
from database.session import get_db
from memory.schemas import MemoryCreate, MemoryRead, MemorySearchResult
from memory.service import memory_service
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def store_memory(
    payload: MemoryCreate, db: DbSession, _: CurrentUser
) -> MemoryRead:
    try:
        record = await memory_service.store(
            db,
            content=payload.content,
            source=payload.source,
            contact_id=payload.contact_id,
        )
    except Exception as exc:  # noqa: BLE001 - surface infra failures as 503
        logger.error("Memory store failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector store unavailable",
        ) from exc
    return MemoryRead.model_validate(record)


@router.get("/search", response_model=list[MemorySearchResult])
async def search_memory(
    _: CurrentUser,
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
    contact_id: int | None = None,
) -> list[MemorySearchResult]:
    try:
        results = await memory_service.search(
            query=q, limit=limit, contact_id=contact_id
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Memory search failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector store unavailable",
        ) from exc
    return [MemorySearchResult(**result) for result in results]
