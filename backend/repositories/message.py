from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from models.message import Message
from repositories.base import SQLAlchemyRepository


class MessageRepository(SQLAlchemyRepository[Message]):
    model = Message

    async def last_message_by_contact(
        self, contact_ids: list[int]
    ) -> dict[int, Message]:
        """The single most recent message per contact (by
        `provider_timestamp`, falling back to `created_at`) -- one query via
        `ROW_NUMBER` window function, never one query per contact. Feeds the
        cross-contact priority ranking (see
        CONTACT_INTELLIGENCE_ARCHITECTURE.md #13). Works on both Postgres
        (production) and SQLite (tests) -- `DISTINCT ON` is Postgres-only,
        `ROW_NUMBER` is portable to both."""
        if not contact_ids:
            return {}
        order_key = func.coalesce(Message.provider_timestamp, Message.created_at)
        row_number = (
            func.row_number()
            .over(partition_by=Message.contact_id, order_by=order_key.desc())
            .label("row_number")
        )
        subquery = (
            select(Message, row_number)
            .where(Message.contact_id.in_(contact_ids))
            .subquery()
        )
        message_alias = aliased(Message, subquery)
        statement = select(message_alias).where(subquery.c.row_number == 1)
        messages = (await self.session.execute(statement)).scalars().all()
        return {message.contact_id: message for message in messages}

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
