"""Generic CRUD router factory, built on the repository layer.

Builds list/create/get/update/delete endpoints for a model, keeping every
resource router consistent (auth required, pagination, 404 handling) without
repeating the same handlers ten times.
"""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import CurrentUser
from database.base import Base
from database.session import get_db
from repositories.base import SQLAlchemyRepository

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

    class Repository(SQLAlchemyRepository):  # noqa: D401 - closure-scoped repository
        pass

    Repository.model = model

    def _scope(user_id: int) -> dict[str, Any]:
        return {"user_id": user_id} if user_scoped else {}

    async def _get_or_404(repository: Repository, item_id: int, user_id: int) -> Base:
        item = await repository.get(item_id)
        if item is None or (user_scoped and item.user_id != user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{tag} not found")
        return item

    @router.get("", response_model=list[read_schema])
    async def list_items(
        db: DbSession,
        current_user: CurrentUser,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[Base]:
        return await Repository(db).list(limit=limit, offset=offset, **_scope(current_user.id))

    @router.get("/count")
    async def count_items(db: DbSession, current_user: CurrentUser) -> dict[str, int]:
        return {"count": await Repository(db).count(**_scope(current_user.id))}

    @router.post("", response_model=read_schema, status_code=status.HTTP_201_CREATED)
    async def create_item(payload: create_schema, db: DbSession, current_user: CurrentUser) -> Base:  # type: ignore[valid-type]
        data = payload.model_dump()
        if user_scoped:
            data["user_id"] = current_user.id
        return await Repository(db).create(**data)

    @router.get("/{item_id}", response_model=read_schema)
    async def get_item(item_id: int, db: DbSession, current_user: CurrentUser) -> Base:
        return await _get_or_404(Repository(db), item_id, current_user.id)

    @router.patch("/{item_id}", response_model=read_schema)
    async def update_item(
        item_id: int, payload: update_schema, db: DbSession, current_user: CurrentUser  # type: ignore[valid-type]
    ) -> Base:
        repository = Repository(db)
        item = await _get_or_404(repository, item_id, current_user.id)
        return await repository.update(item, **payload.model_dump(exclude_unset=True))

    @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_item(item_id: int, db: DbSession, current_user: CurrentUser) -> None:
        repository = Repository(db)
        item = await _get_or_404(repository, item_id, current_user.id)
        await repository.delete(item)

    return router
