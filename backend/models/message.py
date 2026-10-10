import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin


class MessageDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageMediaType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf"
    AUDIO = "audio"
    LOCATION = "location"


class MessageDeliveryStatus(str, enum.Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection), nullable=False
    )
    media_type: Mapped[MessageMediaType] = mapped_column(
        Enum(MessageMediaType), default=MessageMediaType.TEXT
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Provider message id; unique (NULLs excluded) so a redelivered webhook
    # can never create a duplicate row — see webhooks/router.py's dedup check.
    external_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, index=True
    )
    # The provider's own event timestamp, when reported (protects message
    # ordering against out-of-order webhook delivery). Falls back to
    # created_at (arrival order) when the provider doesn't report one.
    provider_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Delivery/read receipt, updated by an onAck-style webhook event when the
    # provider's transport supports it (see WhatsAppProvider.parse_delivery_ack).
    delivery_status: Mapped[MessageDeliveryStatus | None] = mapped_column(
        Enum(MessageDeliveryStatus)
    )
    # Who actually authored an OUTBOUND row: the owner/attendant typing from
    # their own phone (sent_by_human=True, see webhooks/router.py's
    # _capture_human_reply) vs. an agent's automatic reply
    # (is_autopilot_reply=True, see jobs/handlers.py's send_whatsapp_text).
    # Added via e610080003 -- confirmed already present in production
    # (\d messages against darioos_cutover_20260927) before this repo had
    # any migration for it.
    sent_by_human: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_autopilot_reply: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Which Evolution gateway instance this message belongs to (personal,
    # store, b2b-sales, azusa-church, ...). Nullable: older rows and
    # single-instance deployments never set it.
    whatsapp_instance: Mapped[str | None] = mapped_column(String(128), index=True)

    contact = relationship("Contact", back_populates="messages")
