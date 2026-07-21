from sqlalchemy import select

from models.app_setting import AppSetting
from repositories.base import SQLAlchemyRepository


class AppSettingRepository(SQLAlchemyRepository[AppSetting]):
    model = AppSetting

    async def get_by_key(self, key: str) -> AppSetting | None:
        return await self.find_one(key=key)

    async def list_all(self) -> list[AppSetting]:
        result = await self.session.execute(
            select(AppSetting).order_by(AppSetting.category, AppSetting.key)
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        key: str,
        value: str,
        description: str,
        category: str,
        editable: bool,
        updated_by: int | None,
    ) -> AppSetting:
        existing = await self.get_by_key(key)
        if existing is not None:
            return await self.update(
                existing,
                value=value,
                description=description,
                category=category,
                editable=editable,
                updated_by=updated_by,
            )
        return await self.create(
            key=key,
            value=value,
            description=description,
            category=category,
            editable=editable,
            updated_by=updated_by,
        )
