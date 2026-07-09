from sqlalchemy import select

from models.message import Message
from repositories.base import SQLAlchemyRepository


class MessageRepository(SQLAlchemyRepository[Message]):
    model = Message

    async def recent_for_contact(self, contact_id: int, limit: int = 20) -> list[Message]:
        statement = (
            select(Message)
            .where(Message.contact_id == contact_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        messages = list((await self.session.execute(statement)).scalars().all())
        return list(reversed(messages))  # chronological order
