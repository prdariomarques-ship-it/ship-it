"""One row per active suspension of automatic outbound WhatsApp.

The primary key IS the scope (`global` or `instance:<name>`), so "suspend" and
"resume" are single-row INSERT / DELETE statements: two concurrent edits of
different scopes can never overwrite each other (the former comma-separated
`app_settings` value was a read-modify-write race), and the state is shared by
every process that reads the database.

The absence of a row means "not suspended". Rows are never soft-deleted: the
history lives in the audit log (`source="automation_suspension"`).
"""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin

SCOPE_GLOBAL = "global"
SCOPE_INSTANCE_PREFIX = "instance:"


def instance_scope(instance: str) -> str:
    return f"{SCOPE_INSTANCE_PREFIX}{instance}"


class AutomationSuspension(Base, TimestampMixin):
    __tablename__ = "automation_suspensions"

    scope: Mapped[str] = mapped_column(String(80), primary_key=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
