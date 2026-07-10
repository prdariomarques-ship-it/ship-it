from sqlalchemy.exc import IntegrityError

from models.email_account import EmailAccount
from repositories.base import SQLAlchemyRepository


class EmailAccountRepository(SQLAlchemyRepository[EmailAccount]):
    model = EmailAccount

    async def get_by_user(self, user_id: int, provider: str) -> EmailAccount | None:
        return await self.find_one(user_id=user_id, provider=provider)

    async def upsert_for_user(self, user_id: int, provider: str, **fields: object) -> EmailAccount:
        """Create or update the (user, provider) row, recovering from the
        unique-constraint race where two concurrent OAuth callbacks for the
        same user both see no existing row and both attempt to create one —
        same recovery idiom as `ContactRepository.get_or_create_by_phone`."""
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
