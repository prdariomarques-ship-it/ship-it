"""notes pinned, archived, contact_id

Revision ID: a1f9c3d84e2b
Revises: 389bdd08a97f
Create Date: 2026-07-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1f9c3d84e2b"
down_revision: Union[str, None] = "389bdd08a97f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default so existing rows (nullable=False) get a real value
    # rather than failing the ALTER TABLE outright.
    op.add_column(
        "notes",
        sa.Column(
            "pinned", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "notes",
        sa.Column(
            "archived", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "notes", sa.Column("contact_id", sa.Integer(), nullable=True)
    )
    op.create_index(
        op.f("ix_notes_contact_id"), "notes", ["contact_id"], unique=False
    )
    op.create_foreign_key(
        "fk_notes_contact_id_contacts",
        "notes",
        "contacts",
        ["contact_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_notes_contact_id_contacts", "notes", type_="foreignkey")
    op.drop_index(op.f("ix_notes_contact_id"), table_name="notes")
    op.drop_column("notes", "contact_id")
    op.drop_column("notes", "archived")
    op.drop_column("notes", "pinned")
