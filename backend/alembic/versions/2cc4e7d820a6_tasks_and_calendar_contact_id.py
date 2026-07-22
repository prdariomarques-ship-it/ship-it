"""tasks and calendar contact_id

Revision ID: 2cc4e7d820a6
Revises: 68ff6ab67cdd
Create Date: 2026-07-21 23:05:36.180992

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2cc4e7d820a6'
down_revision: Union[str, None] = '68ff6ab67cdd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, additive -- same pattern as notes.contact_id
    # (a1f9c3d84e2b): a row only ever gets one when a task/event is
    # explicitly linked to a contact (Contact Workspace, Release 1.5 P0-2);
    # existing rows are simply unlinked, not migrated to any value.
    op.add_column("tasks", sa.Column("contact_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_tasks_contact_id"), "tasks", ["contact_id"], unique=False)
    op.create_foreign_key(
        "fk_tasks_contact_id_contacts",
        "tasks",
        "contacts",
        ["contact_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("calendar", sa.Column("contact_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_calendar_contact_id"), "calendar", ["contact_id"], unique=False
    )
    op.create_foreign_key(
        "fk_calendar_contact_id_contacts",
        "calendar",
        "contacts",
        ["contact_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_calendar_contact_id_contacts", "calendar", type_="foreignkey"
    )
    op.drop_index(op.f("ix_calendar_contact_id"), table_name="calendar")
    op.drop_column("calendar", "contact_id")

    op.drop_constraint("fk_tasks_contact_id_contacts", "tasks", type_="foreignkey")
    op.drop_index(op.f("ix_tasks_contact_id"), table_name="tasks")
    op.drop_column("tasks", "contact_id")
