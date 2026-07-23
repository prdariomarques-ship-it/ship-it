from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin


class Contact(Base, TimestampMixin):
    """A person Dario OS knows about — the core of the permanent memory.

    Deliberately has no `user_id`/owner column -- a single shared address
    book, correct only because Release 1.x supports exactly one operator.
    This is a documented, hard architectural constraint, not an oversight:
    see docs/adr/ADR-0002-single-operator-constraint.md for what must be
    redesigned (this model included) before any second real user account
    is ever created."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    categories: Mapped[list] = mapped_column(
        JSON, default=list
    )  # e.g. ["igreja", "loja"]
    summary: Mapped[str | None] = mapped_column(Text)  # AI-maintained profile summary
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    last_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    messages = relationship(
        "Message", back_populates="contact", cascade="all, delete-orphan"
    )
