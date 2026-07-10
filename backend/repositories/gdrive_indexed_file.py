from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.gdrive_indexed_file import GoogleDriveIndexedFile
from repositories.base import SQLAlchemyRepository


class GoogleDriveIndexedFileRepository(SQLAlchemyRepository[GoogleDriveIndexedFile]):
    model = GoogleDriveIndexedFile

    async def get_by_user_and_file(self, user_id: int, file_id: str) -> GoogleDriveIndexedFile | None:
        return await self.find_one(user_id=user_id, file_id=file_id)

    async def list_by_user(self, user_id: int, limit: int = 50) -> list[GoogleDriveIndexedFile]:
        """Oldest-indexed first — `update_google_drive_index` refreshes the
        staleset entries first when bounded by `limit`."""
        statement = (
            select(self.model)
            .where(self.model.user_id == user_id)
            .order_by(self.model.indexed_at.asc())
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def upsert_for_user_and_file(self, user_id: int, file_id: str, **fields: object) -> GoogleDriveIndexedFile:
        """Same race-safe create-or-update idiom as
        `GoogleDriveAccountRepository.upsert_for_user` — two concurrent
        indexing calls for the same file must not crash on the unique
        constraint."""
        existing = await self.get_by_user_and_file(user_id, file_id)
        if existing is not None:
            return await self.update(existing, **fields)

        item = self.model(user_id=user_id, file_id=file_id, **fields)
        self.session.add(item)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.get_by_user_and_file(user_id, file_id)
            if existing is None:
                raise
            return await self.update(existing, **fields)
        await self.session.refresh(item)
        return item
