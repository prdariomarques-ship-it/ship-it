from models.user import User
from repositories.base import SQLAlchemyRepository


class UserRepository(SQLAlchemyRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        return await self.find_one(email=email)
