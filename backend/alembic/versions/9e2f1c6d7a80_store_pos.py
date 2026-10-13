"""Persist POS drafts and manual payment audit without duplicating the catalog."""
from alembic import op
import sqlalchemy as sa

revision = "9e2f1c6d7a80"
down_revision = "7d31a9b4e2c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "store_pos_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("store_customers.id"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payment_method", sa.String(20)),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("paid_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_store_pos_orders_customer_id", "store_pos_orders", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_store_pos_orders_customer_id", table_name="store_pos_orders")
    op.drop_table("store_pos_orders")
