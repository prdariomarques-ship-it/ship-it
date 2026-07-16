from sqlalchemy import func, select

from models.message import Message
from repositories.base import SQLAlchemyRepository


class MessageRepository(SQLAlchemyRepository[Message]):
    model = Message

    async def recent_for_contact(
        self, contact_id: int, limit: int = 20
    ) -> list[Message]:
        # Order by the provider's own timestamp when it reported one (protects
        # against out-of-order webhook delivery); fall back to arrival order
        # (id) for messages with no provider timestamp.
        order_key = func.coalesce(Message.provider_timestamp, Message.created_at)
        statement = (
            select(Message)
            .where(Message.contact_id == contact_id)
            .order_by(order_key.desc(), Message.id.desc())
            .limit(limit)
        )
        messages = list((await self.session.execute(statement)).scalars().all())
        return list(reversed(messages))  # chronological order

    async def get_by_external_id(self, external_id: str) -> Message | None:
        return await self.find_one(external_id=external_id)
