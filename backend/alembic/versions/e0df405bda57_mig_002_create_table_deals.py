"""MIG-002: Create table deals

Revision ID: e0df405bda57
Revises: daa5cef5165c
Create Date: 2026-07-12 16:32:56.830235

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e0df405bda57"
down_revision: Union[str, None] = "daa5cef5165c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deals",
        sa.Column("id", sa.BIGINT(), nullable=False, autoincrement=True),
        sa.Column("client_id", sa.BIGINT(), nullable=False),
        sa.Column("title", sa.VARCHAR(length=255), nullable=False),
        sa.Column("value", sa.NUMERIC(precision=12, scale=2), nullable=True),
        sa.Column("status", sa.VARCHAR(length=50), nullable=True),
        sa.Column("expected_close_date", sa.DATE(), nullable=True),
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
            ["client_id"],
            ["clients.id"],
        ),
    )
    op.create_index("deals_client_id_idx", "deals", ["client_id"])
    op.create_index("deals_status_idx", "deals", ["status"])
    op.create_index("deals_expected_close_idx", "deals", ["expected_close_date"])
    op.create_index("deals_created_at_idx", "deals", ["created_at"])


def downgrade() -> None:
    op.drop_index("deals_created_at_idx", table_name="deals")
    op.drop_index("deals_expected_close_idx", table_name="deals")
    op.drop_index("deals_status_idx", table_name="deals")
    op.drop_index("deals_client_id_idx", table_name="deals")
    op.drop_table("deals")
