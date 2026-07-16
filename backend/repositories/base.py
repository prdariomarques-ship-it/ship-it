"""Generic async repository (Repository pattern).

Encapsulates persistence so services and routers never build SQLAlchemy
queries directly; specialized repositories extend this with domain queries.
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class SQLAlchemyRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, item_id: int) -> ModelT | None:
        return await self.session.get(self.model, item_id)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        order_desc: bool = True,
        **filters: Any,
    ) -> list[ModelT]:
        statement = select(self.model)
        for field, value in filters.items():
            statement = statement.where(getattr(self.model, field) == value)
        order = self.model.id.desc() if order_desc else self.model.id.asc()  # type: ignore[attr-defined]
        result = await self.session.execute(
            statement.order_by(order).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def count(self, **filters: Any) -> int:
        statement = select(func.count()).select_from(self.model)
        for field, value in filters.items():
            statement = statement.where(getattr(self.model, field) == value)
        return (await self.session.execute(statement)).scalar_one()

    async def find_one(self, **filters: Any) -> ModelT | None:
        statement = select(self.model)
        for field, value in filters.items():
            statement = statement.where(getattr(self.model, field) == value)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def create(self, **data: Any) -> ModelT:
        item = self.model(**data)
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def update(self, item: ModelT, **data: Any) -> ModelT:
        for field, value in data.items():
            setattr(item, field, value)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def delete(self, item: ModelT) -> None:
        await self.session.delete(item)
        await self.session.commit()
