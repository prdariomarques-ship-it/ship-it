from sqlalchemy.exc import IntegrityError

from models.gcontacts_account import GoogleContactsAccount
from repositories.base import SQLAlchemyRepository


class GoogleContactsAccountRepository(SQLAlchemyRepository[GoogleContactsAccount]):
    model = GoogleContactsAccount

    async def get_by_user(self, user_id: int, provider: str) -> GoogleContactsAccount | None:
        return await self.find_one(user_id=user_id, provider=provider)

    async def upsert_for_user(self, user_id: int, provider: str, **fields: object) -> GoogleContactsAccount:
        """Same race-safe create-or-update idiom as
        `GoogleCalendarAccountRepository.upsert_for_user` — see there for
        the full rationale."""
        existing = await self.get_by_user(user_id, provider)
        if existing is not None:
            return await self.update(existing, **fields)

        item = self.model(user_id=user_id, provider=provider, **fields)
        self.session.add(item)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.get_by_user(user_id, provider)
            if existing is None:
                raise
            return await self.update(existing, **fields)
        await self.session.refresh(item)
        return item
