from models.email_account import EmailAccount
from repositories.base import SQLAlchemyRepository


class EmailAccountRepository(SQLAlchemyRepository[EmailAccount]):
    model = EmailAccount

    async def get_by_user(self, user_id: int, provider: str) -> EmailAccount | None:
        return await self.find_one(user_id=user_id, provider=provider)
