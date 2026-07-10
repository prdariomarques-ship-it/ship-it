import enum

from sqlalchemy import Enum, ForeignKey, String, Text
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


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    direction: Mapped[MessageDirection] = mapped_column(Enum(MessageDirection), nullable=False)
    media_type: Mapped[MessageMediaType] = mapped_column(Enum(MessageMediaType), default=MessageMediaType.TEXT)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Provider message id; unique (NULLs excluded) so a redelivered webhook
    # can never create a duplicate row — see webhooks/router.py's dedup check.
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)

    contact = relationship("Contact", back_populates="messages")
