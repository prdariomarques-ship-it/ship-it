from sqlalchemy.exc import IntegrityError

from models.gcalendar_account import GoogleCalendarAccount
from repositories.base import SQLAlchemyRepository


class GoogleCalendarAccountRepository(SQLAlchemyRepository[GoogleCalendarAccount]):
    model = GoogleCalendarAccount

    async def get_by_user(self, user_id: int, provider: str) -> GoogleCalendarAccount | None:
        return await self.find_one(user_id=user_id, provider=provider)

    async def upsert_for_user(self, user_id: int, provider: str, **fields: object) -> GoogleCalendarAccount:
        """Create or update the (user, provider) row, recovering from the
        unique-constraint race where two concurrent OAuth callbacks for the
        same user both see no existing row and both attempt to create one —
        same idiom as `EmailAccountRepository.upsert_for_user` and
        `ContactRepository.get_or_create_by_phone` (found and fixed as a
        real bug during the Sprint 1.1 Gmail audit; applied here from the
        start instead of waiting for a follow-up pass)."""
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
