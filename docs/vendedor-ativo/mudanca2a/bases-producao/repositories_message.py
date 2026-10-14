from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from models.message import Message, MessageDirection
from repositories.base import SQLAlchemyRepository


class MessageRepository(SQLAlchemyRepository[Message]):
    model = Message

    async def has_human_reply_after(self, message: Message) -> bool:
        timestamp = message.provider_timestamp or message.created_at
        statement = select(Message.id).where(
            Message.contact_id == message.contact_id,
            Message.whatsapp_instance == message.whatsapp_instance,
            Message.direction == MessageDirection.OUTBOUND,
            Message.sent_by_human.is_(True),
            func.coalesce(Message.provider_timestamp, Message.created_at) >= timestamp,
        ).limit(1)
        return (await self.session.execute(statement)).scalar_one_or_none() is not None

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
        self, contact_id: int, limit: int = 20, instance: str | None = None
    ) -> list[Message]:
        order_key = func.coalesce(Message.provider_timestamp, Message.created_at)
        conditions = [Message.contact_id == contact_id]
        if instance:
            conditions.append(Message.whatsapp_instance == instance)

        statement = (
            select(Message)
            .where(*conditions)
            .order_by(order_key.desc(), Message.id.desc())
            .limit(limit)
        )
        messages = list((await self.session.execute(statement)).scalars().all())
        return list(reversed(messages))

    async def get_latest_inbound(
        self, contact_id: int, instance: str | None = None
    ) -> Message | None:
        order_key = func.coalesce(Message.provider_timestamp, Message.created_at)
        conditions = [
            Message.contact_id == contact_id,
            Message.direction == MessageDirection.INBOUND,
        ]
        if instance:
            conditions.append(Message.whatsapp_instance == instance)

        statement = (
            select(Message)
            .where(*conditions)
            .order_by(order_key.desc(), Message.id.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalars().first()

    async def find_unacknowledged_outbound(
        self,
        contact_id: int,
        content: str,
        within_seconds: int = 120,
        instance: str | None = None,
    ) -> Message | None:
        since = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)

        conditions = [
            Message.contact_id == contact_id,
            Message.direction == MessageDirection.OUTBOUND,
            Message.sent_by_human.is_(False),
            Message.external_id.is_(None),
            Message.content == content,
            Message.created_at >= since,
        ]

        if instance:
            conditions.append(Message.whatsapp_instance == instance)

        statement = (
            select(Message)
            .where(*conditions)
            .order_by(Message.id.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalars().first()

    async def get_by_external_id(self, external_id: str) -> Message | None:
        return await self.find_one(external_id=external_id)
