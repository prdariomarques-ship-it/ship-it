"""Goal: a persistent objective the owner (or an agent, on their behalf)
tracks over time — distinct from `Task` (a simple reminder/to-do surfaced to
the user). A Goal can depend on other goals, carry a deadline, and recur.
"""
import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class GoalStatus(str, enum.Enum):
    # A goal created with requires_approval=True starts here and is excluded
    # from ready_goals() until an admin calls GoalService.approve_goal — the
    # human-approval gate. Goals created without requires_approval skip this
    # status entirely and start at PENDING.
    AWAITING_APPROVAL = "awaiting_approval"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class GoalPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Goal(Base, TimestampMixin):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[GoalStatus] = mapped_column(Enum(GoalStatus), default=GoalStatus.PENDING, index=True)
    priority: Mapped[GoalPriority] = mapped_column(Enum(GoalPriority), default=GoalPriority.MEDIUM)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Human approval workflow.
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # Recurrence: a fixed interval in days rather than a cron/RRULE string —
    # deliberately simple (daily/weekly/monthly are just 1/7/30) and fully
    # testable; see docs/GOALS.md for the trade-off. When a recurring goal is
    # marked COMPLETED, GoalService spawns a new Goal row for the next
    # occurrence instead of mutating this one, so history is never lost.
    recurrence_interval_days: Mapped[int | None] = mapped_column(Integer)
    # Always points at the *original* goal of a recurrence chain (never at the
    # immediately preceding occurrence), so every occurrence can be traced
    # back to where the recurrence started with a single lookup.
    recurrence_parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), index=True
    )


class GoalDependency(Base):
    """Directed edge: `goal_id` cannot proceed until `depends_on_id` is COMPLETED."""

    __tablename__ = "goal_dependencies"
    __table_args__ = (UniqueConstraint("goal_id", "depends_on_id", name="uq_goal_dependency"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    depends_on_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
