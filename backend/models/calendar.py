from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class CalendarEvent(Base, TimestampMixin):
    __tablename__ = "calendar"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_minutes: Mapped[int | None] = mapped_column()
    # Nullable, additive -- same reserved-until-linked pattern as
    # Note.contact_id/Task.contact_id. See docs/CONTACTS.md (Contact
    # Workspace, Release 1.5 P0-2).
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
