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
    repository_cls: type[SQLAlchemyRepository] | None = None,
) -> APIRouter:
    """Build a CRUD router. When user_scoped, rows belong to the current user.

    `repository_cls`, when given, is used instead of an anonymous
    `SQLAlchemyRepository` subclass -- lets a resource with a specialized
    repository (e.g. `ContactRepository.search_by_name`) keep using it
    through this shared factory rather than losing it to a generic one.
    """
    router = APIRouter(prefix=prefix, tags=[tag])

    class _AnonymousRepository(SQLAlchemyRepository):  # noqa: D401 - closure-scoped
        pass

    _AnonymousRepository.model = model  # type: ignore[misc]

    Repository: type[SQLAlchemyRepository] = (
        repository_cls if repository_cls is not None else _AnonymousRepository
    )
    searchable = hasattr(Repository, "search_by_name")

    def _scope(user_id: int) -> dict[str, Any]:
        return {"user_id": user_id} if user_scoped else {}

    async def _get_or_404(
        repository: SQLAlchemyRepository, item_id: int, user_id: int
    ) -> Base:
        item = await repository.get(item_id)
        if item is None or (user_scoped and item.user_id != user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{tag} not found"
            )
        return item

    # Two variants rather than one `q: str | None = None` param always
    # present: a resource whose repository has no `search_by_name` (tasks,
    # store) shouldn't advertise a query param that would silently do
    # nothing. Distinct function names (not both `list_items`) so mypy
    # doesn't see this as one function redefined with an incompatible
    # signature -- only one of the two is ever registered as a route.
    if searchable:

        @router.get("", response_model=list[read_schema])  # type: ignore[valid-type]
        async def list_items_searchable(
            db: DbSession,
            current_user: CurrentUser,
            q: Annotated[str | None, Query(description="Search by name")] = None,
            limit: Annotated[int, Query(ge=1, le=200)] = 50,
            offset: Annotated[int, Query(ge=0)] = 0,
        ) -> list[Base]:
            repository = Repository(db)
            if q:
                # search_by_name has no offset param -- acceptable for a
                # personal-scale system, see docs (not paginated by design).
                return await repository.search_by_name(q, limit=limit)  # type: ignore[attr-defined]
            return await repository.list(
                limit=limit, offset=offset, **_scope(current_user.id)
            )
    else:

        @router.get("", response_model=list[read_schema])  # type: ignore[valid-type]
        async def list_items_plain(
            db: DbSession,
            current_user: CurrentUser,
            limit: Annotated[int, Query(ge=1, le=200)] = 50,
            offset: Annotated[int, Query(ge=0)] = 0,
        ) -> list[Base]:
            return await Repository(db).list(
                limit=limit, offset=offset, **_scope(current_user.id)
            )

    @router.get("/count")
    async def count_items(db: DbSession, current_user: CurrentUser) -> dict[str, int]:
        return {"count": await Repository(db).count(**_scope(current_user.id))}

    @router.post("", response_model=read_schema, status_code=status.HTTP_201_CREATED)
    async def create_item(
        payload: create_schema,  # type: ignore[valid-type]
        db: DbSession,
        current_user: CurrentUser,
    ) -> Base:
        data = payload.model_dump()  # type: ignore[attr-defined]
        if user_scoped:
            data["user_id"] = current_user.id
        return await Repository(db).create(**data)

    @router.get("/{item_id}", response_model=read_schema)
    async def get_item(item_id: int, db: DbSession, current_user: CurrentUser) -> Base:
        return await _get_or_404(Repository(db), item_id, current_user.id)

    @router.patch("/{item_id}", response_model=read_schema)
    async def update_item(
        item_id: int,
        payload: update_schema,  # type: ignore[valid-type]
        db: DbSession,
        current_user: CurrentUser,
    ) -> Base:
        repository = Repository(db)
        item = await _get_or_404(repository, item_id, current_user.id)
        return await repository.update(item, **payload.model_dump(exclude_unset=True))  # type: ignore[attr-defined]

    @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_item(
        item_id: int, db: DbSession, current_user: CurrentUser
    ) -> None:
        repository = Repository(db)
        item = await _get_or_404(repository, item_id, current_user.id)
        await repository.delete(item)

    return router
