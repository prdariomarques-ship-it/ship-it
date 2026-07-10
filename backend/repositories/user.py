from sqlalchemy import select

from models.user import User, UserRole
from repositories.base import SQLAlchemyRepository


class UserRepository(SQLAlchemyRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        return await self.find_one(email=email)

    async def get_first_admin(self) -> User | None:
        """The account background flows (WhatsApp auto-reply) act on behalf of.

        Dario OS is a single-owner personal system, not multi-tenant, so
        tool actions triggered by an inbound WhatsApp message (create a task,
        add an event, ...) belong to the instance's owner — the first admin —
        rather than to the contact who sent the message. Ordered by id (not
        `find_one`) because nothing stops a second admin from existing later.
        """
        statement = select(User).where(User.role == UserRole.ADMIN).order_by(User.id.asc()).limit(1)
        return (await self.session.execute(statement)).scalar_one_or_none()
