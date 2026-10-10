from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
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
        self, contact_id: int, limit: int = 20, instance: str | None = None,
    ) -> list[Message]:
        # Order by the provider's own timestamp when it reported one (protects
        # against out-of-order webhook delivery); fall back to arrival order
        # (id) for messages with no provider timestamp.
        #
        # Review finding (round 6, "reconciliar a base"): jobs/handlers.py's
        # owner-audio pipeline has always called this with `instance=` (its
        # per-instance conversation history digest -- see
        # _owner_audio_refresh_history/_owner_audio_history_digest -- would
        # be meaningless mixing in a different gateway instance's unrelated
        # thread), but this method never accepted it, a guaranteed TypeError
        # on every call. Optional and additive: every other caller
        # (memory/contact_memory.py, memory/manager.py,
        # api/contact_workspace.py) omits it and keeps its exact old,
        # all-instances behavior.
        order_key = func.coalesce(Message.provider_timestamp, Message.created_at)
        statement = (
            select(Message)
            .where(Message.contact_id == contact_id)
            .order_by(order_key.desc(), Message.id.desc())
            .limit(limit)
        )
        if instance:
            statement = statement.where(Message.whatsapp_instance == instance)
        messages = list((await self.session.execute(statement)).scalars().all())
        return list(reversed(messages))  # chronological order

    async def get_by_external_id(self, external_id: str) -> Message | None:
        return await self.find_one(external_id=external_id)

    async def get_latest_inbound(self, contact_id: int, instance: str | None = None) -> Message | None:
        """The single most recent INBOUND message for this contact
        (optionally scoped to `instance`) -- same ordering convention as
        `recent_for_contact`/`last_message_by_contact` (provider timestamp,
        falling back to arrival order).

        Review finding (round 6): jobs/handlers.py's twin-autopilot-check
        job calls this to detect whether the inbound message that
        triggered it (`message_id`) is still the LATEST one, or whether a
        newer inbound message has arrived since it was enqueued (in which
        case this stale check must no-op rather than act on outdated
        context) -- but this method never existed, a guaranteed
        AttributeError every time that job ran."""
        order_key = func.coalesce(Message.provider_timestamp, Message.created_at)
        statement = (
            select(Message)
            .where(Message.contact_id == contact_id, Message.direction == MessageDirection.INBOUND)
            .order_by(order_key.desc(), Message.id.desc())
            .limit(1)
        )
        if instance:
            statement = statement.where(Message.whatsapp_instance == instance)
        return (await self.session.execute(statement)).scalars().first()

    async def has_human_reply_after(self, message: Message) -> bool:
        """Whether a human-sent (`sent_by_human=True`) OUTBOUND message
        exists for this message's exact (contact_id, whatsapp_instance)
        scope, ordered strictly after it -- same tie-breaking convention
        used everywhere else in this module (provider_timestamp, falling
        back to created_at, `id` as the final tiebreak for same-timestamp
        rows).

        Review finding (round 6): jobs/handlers.py's
        `transcribe_whatsapp_audio` calls this to detect an owner reply
        that arrived WHILE a voice note was being transcribed, so the
        delayed auto-reply dispatch doesn't re-arm automation the human
        already handled -- but it never existed, a guaranteed
        AttributeError on every audio message. Mirrors the inline
        "newer_human" query jobs/handlers.py's `_owner_audio_turn_current`
        already implements for the identical purpose (not duplicated
        logic invented fresh -- the same, already-working comparison,
        exposed here as a reusable method for this second call site)."""
        timestamp = message.provider_timestamp or message.created_at
        order_key = func.coalesce(Message.provider_timestamp, Message.created_at)
        statement = (
            select(Message.id)
            .where(
                Message.contact_id == message.contact_id,
                Message.whatsapp_instance == message.whatsapp_instance,
                Message.direction == MessageDirection.OUTBOUND,
                Message.sent_by_human.is_(True),
                or_(order_key > timestamp, and_(order_key == timestamp, Message.id > message.id)),
            )
            .limit(1)
        )
        return (await self.session.execute(statement)).scalars().first() is not None

    async def find_unacknowledged_outbound(
        self, contact_id: int, text: str, instance: str | None = None,
        within_seconds: float | None = None,
    ) -> Message | None:
        """Locate WHICH unacknowledged outbound row a fromMe webhook event's
        provider identifier -- already proven to be this system's own echo
        by the caller -- belongs to. Review finding #3 (round 6): this
        function must NEVER be used to DECIDE whether something is an echo.
        Content equality is not evidence of authorship: a human typing the
        exact words of an old, stuck, never-acknowledged autopilot send is
        indistinguishable from a genuine echo by text alone, and the first
        version of this function (round 4) returned a match purely on
        content/instance/unacknowledged-state, with no bound on age --
        letting that coincidence suppress a real human-takeover pause.

        Callers MUST independently establish echo authorship first (see
        webhooks/router.py's `_capture_human_reply`, which checks
        `services.conversation_control.known_receipt` -- a provider
        identifier recorded from OUR OWN send's response, before any
        webhook can arrive -- and only calls this function once that proof
        already holds). This function's only job after that point is
        finding the specific row to attach the proven receipt to:

          - an OUTBOUND message for this contact, in this same `instance`
            scope (when given -- a contact can have independent outbound
            history across more than one gateway instance, e.g. personal
            vs. store; omitting the filter would risk matching the wrong
            one's content by coincidence);
          - NOT `sent_by_human` -- a real human-reply row (created by this
            same caller on an earlier call) is never a candidate here;
          - unacknowledged (`external_id IS NULL`) -- `persist_outbound_message`
            never sets it, so every row this system sends starts out this
            way; a row that already has one was a previous, different
            send and must not be reused;
          - identical `content` to the echoed text;
          - created within `within_seconds` of now, when given -- pure
            hygiene against matching an unrelated stale send that happens
            to share the same text, never a substitute for the caller's
            own proof.

        Returns the most recent match, or None -- a None here (with the
        caller's echo proof already established independently) means the
        proven echo has no row left to attach to, not that this is a
        human message; see _capture_human_reply's `own_echo_unmatched`
        handling.
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
        if within_seconds is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
            statement = statement.where(Message.created_at >= cutoff)
        return (await self.session.execute(statement)).scalars().first()
