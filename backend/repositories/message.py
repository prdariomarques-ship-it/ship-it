from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from models.message import Message, MessageDirection
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

    async def find_unacknowledged_outbound(
        self, contact_id: int, text: str, instance: str | None = None
    ) -> Message | None:
        """Match a `fromMe=True` webhook event back to the row THIS system
        already created for it -- distinguishing the automation's own
        delivery echo from a genuine human reply typed directly on the
        phone. Review finding #2 (round 4): `webhooks/router.py`'s
        `_capture_human_reply` has always called this to make exactly that
        distinction, but it never existed in this repository.

        A candidate row must be:
          - an OUTBOUND message for this contact, in this same `instance`
            scope (when given -- a contact can have independent outbound
            history across more than one gateway instance, e.g. personal
            vs. store; omitting the filter would risk matching the wrong
            one's content by coincidence);
          - NOT `sent_by_human` -- a real human-reply row (created by this
            same function on an earlier call) is never a candidate here.
            Matching one would treat a second genuine reply as if it were
            an echo of the first, which is exactly the "não trate todo
            fromMe como humano" failure mode in reverse: this function's
            job is to find OUR OWN system's send, not any outbound row;
          - unacknowledged (`external_id IS NULL`) -- `persist_outbound_message`
            never sets it, so every row this system sends starts out this
            way; a row that already has one was a previous, different
            send and must not be reused;
          - identical `content` to the echoed text -- the only signal
            available, since no provider-side request id is persisted at
            send time to correlate against instead (a separate, documented
            gap: see jobs/handlers.py's send_whatsapp_text, which computes
            a receipt id but never writes it back onto this row).

        Returns the most recent match (there should only ever be one
        unacknowledged row at a time for a given instance, since every
        send is followed by a commit before the next one can start) or
        None -- a None here is what tells the caller this is a genuinely
        new human-typed message, not an echo of anything this system sent.
        """
        statement = (
            select(Message)
            .where(
                Message.contact_id == contact_id,
                Message.direction == MessageDirection.OUTBOUND,
                Message.sent_by_human.is_(False),
                Message.external_id.is_(None),
                Message.content == text,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        if instance:
            statement = statement.where(Message.whatsapp_instance == instance)
        return (await self.session.execute(statement)).scalars().first()
