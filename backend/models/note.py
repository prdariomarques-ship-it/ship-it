from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class Note(Base, TimestampMixin):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Excluded from the default list view (not deleted) -- lets long-term
    # notes accumulate without cluttering day-to-day capture. No project-wide
    # soft-delete convention exists (checked: no model uses one), so this is
    # deliberately its own lifecycle flag, not a stand-in for deletion.
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Nullable, unused by any endpoint yet -- reserved so a future feature
    # ("link this note to a contact/conversation") is a pure application-layer
    # change, not a migration. See docs/NOTES.md.
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
