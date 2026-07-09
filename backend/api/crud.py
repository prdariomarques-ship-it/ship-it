"""Generic CRUD router factory.

Builds list/create/get/update/delete endpoints for a model, keeping every
resource router consistent (auth required, pagination, 404 handling) without
repeating the same handlers ten times.
"""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import CurrentUser
from database.base import Base
from database.session import get_db

DbSession = Annotated[AsyncSession, Depends(get_db)]


def create_crud_router(
    *,
    model: type[Base],
    prefix: str,
    tag: str,
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    read_schema: type[BaseModel],
    user_scoped: bool = False,
) -> APIRouter:
    """Build a CRUD router. When user_scoped, rows belong to the current user."""
    router = APIRouter(prefix=prefix, tags=[tag])

    def _scope(statement: Any, user_id: int) -> Any:
        return statement.where(model.user_id == user_id) if user_scoped else statement

    async def _get_or_404(db: AsyncSession, item_id: int, user_id: int) -> Base:
        statement = _scope(select(model).where(model.id == item_id), user_id)
        item = (await db.execute(statement)).scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{tag} not found")
        return item

    @router.get("", response_model=list[read_schema])
    async def list_items(
        db: DbSession,
        current_user: CurrentUser,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[Base]:
        statement = _scope(select(model), current_user.id).order_by(model.id.desc()).limit(limit).offset(offset)
        return list((await db.execute(statement)).scalars().all())

    @router.get("/count")
    async def count_items(db: DbSession, current_user: CurrentUser) -> dict[str, int]:
        statement = _scope(select(func.count()).select_from(model), current_user.id)
        return {"count": (await db.execute(statement)).scalar_one()}

    @router.post("", response_model=read_schema, status_code=status.HTTP_201_CREATED)
    async def create_item(payload: create_schema, db: DbSession, current_user: CurrentUser) -> Base:  # type: ignore[valid-type]
        data = payload.model_dump()
        if user_scoped:
            data["user_id"] = current_user.id
        item = model(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @router.get("/{item_id}", response_model=read_schema)
    async def get_item(item_id: int, db: DbSession, current_user: CurrentUser) -> Base:
        return await _get_or_404(db, item_id, current_user.id)

    @router.patch("/{item_id}", response_model=read_schema)
    async def update_item(
        item_id: int, payload: update_schema, db: DbSession, current_user: CurrentUser  # type: ignore[valid-type]
    ) -> Base:
        item = await _get_or_404(db, item_id, current_user.id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        await db.commit()
        await db.refresh(item)
        return item

    @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_item(item_id: int, db: DbSession, current_user: CurrentUser) -> None:
        item = await _get_or_404(db, item_id, current_user.id)
        await db.delete(item)
        await db.commit()

    return router
