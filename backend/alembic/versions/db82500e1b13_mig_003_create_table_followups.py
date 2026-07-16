"""MIG-003: Create table followups

Revision ID: db82500e1b13
Revises: e0df405bda57
Create Date: 2026-07-12 16:33:10.234801

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "db82500e1b13"
down_revision: Union[str, None] = "e0df405bda57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "followups",
        sa.Column("id", sa.BIGINT(), nullable=False, autoincrement=True),
        sa.Column("deal_id", sa.BIGINT(), nullable=False),
        sa.Column("scheduled_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notes", sa.TEXT(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["deal_id"],
            ["deals.id"],
        ),
    )
    op.create_index("followups_deal_id_idx", "followups", ["deal_id"])
    op.create_index("followups_scheduled_at_idx", "followups", ["scheduled_at"])


def downgrade() -> None:
    op.drop_index("followups_scheduled_at_idx", table_name="followups")
    op.drop_index("followups_deal_id_idx", table_name="followups")
    op.drop_table("followups")
