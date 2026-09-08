from sqlalchemy import select

from models.product import Product
from repositories.base import SQLAlchemyRepository


class ProductRepository(SQLAlchemyRepository[Product]):
    model = Product

    async def search_by_name(self, query: str, limit: int = 10) -> list[Product]:
        statement = (
            select(Product)
            .where(Product.active.is_(True))
            .where(Product.name.ilike(f"%{query}%"))
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def get_by_sku(self, sku: str) -> Product | None:
        statement = select(Product).where(Product.sku == sku)
        return (await self.session.execute(statement)).scalar_one_or_none()
