import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.PENDING, index=True
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority), default=TaskPriority.MEDIUM
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Nullable, additive -- same reserved-until-linked pattern as
    # Note.contact_id. Populated either explicitly or automatically when an
    # agent tool creates the task mid-WhatsApp-conversation (ToolContext
    # already carries contact_id there). See docs/CONTACTS.md (Contact
    # Workspace, Release 1.5 P0-2).
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
