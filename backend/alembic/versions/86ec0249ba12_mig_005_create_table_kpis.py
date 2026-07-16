"""MIG-005: Create table kpis

Revision ID: 86ec0249ba12
Revises: 66ce2fcd08b9
Create Date: 2026-07-12 16:33:33.637452

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "86ec0249ba12"
down_revision: Union[str, None] = "66ce2fcd08b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kpis",
        sa.Column("id", sa.BIGINT(), nullable=False, autoincrement=True),
        sa.Column("client_id", sa.BIGINT(), nullable=True),
        sa.Column("deal_id", sa.BIGINT(), nullable=True),
        sa.Column("metric_name", sa.VARCHAR(length=255), nullable=False),
        sa.Column("metric_value", sa.NUMERIC(precision=12, scale=4), nullable=True),
        sa.Column("period", sa.VARCHAR(length=50), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["deal_id"],
            ["deals.id"],
        ),
    )
    op.create_index("kpis_client_id_idx", "kpis", ["client_id"])
    op.create_index("kpis_deal_id_idx", "kpis", ["deal_id"])


def downgrade() -> None:
    op.drop_index("kpis_deal_id_idx", table_name="kpis")
    op.drop_index("kpis_client_id_idx", table_name="kpis")
    op.drop_table("kpis")
