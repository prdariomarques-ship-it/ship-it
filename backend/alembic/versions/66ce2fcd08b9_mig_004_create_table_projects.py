"""MIG-004: Create table projects

Revision ID: 66ce2fcd08b9
Revises: db82500e1b13
Create Date: 2026-07-12 16:33:21.358962

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "66ce2fcd08b9"
down_revision: Union[str, None] = "db82500e1b13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.BIGINT(), nullable=False, autoincrement=True),
        sa.Column("deal_id", sa.BIGINT(), nullable=False),
        sa.Column("name", sa.VARCHAR(length=255), nullable=False),
        sa.Column("status", sa.VARCHAR(length=50), nullable=True),
        sa.Column("budget", sa.NUMERIC(precision=12, scale=2), nullable=True),
        sa.Column(
            "spent",
            sa.NUMERIC(precision=12, scale=2),
            server_default="0",
            nullable=True,
        ),
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
    op.create_index("projects_deal_id_idx", "projects", ["deal_id"])


def downgrade() -> None:
    op.drop_index("projects_deal_id_idx", table_name="projects")
    op.drop_table("projects")
