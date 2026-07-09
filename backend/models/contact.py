from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin


class Contact(Base, TimestampMixin):
    """A person Dario OS knows about — the core of the permanent memory."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    categories: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["igreja", "loja"]
    summary: Mapped[str | None] = mapped_column(Text)  # AI-maintained profile summary
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages = relationship("Message", back_populates="contact", cascade="all, delete-orphan")
