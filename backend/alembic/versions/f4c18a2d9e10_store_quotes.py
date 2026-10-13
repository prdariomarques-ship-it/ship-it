"""Persist customer-owned sales quotes; merge existing independent heads.

Revision ID: f4c18a2d9e10
Revises: 6f32d7549a9a, 2cc4e7d820a6
"""

from alembic import op
import sqlalchemy as sa

revision = "f4c18a2d9e10"
down_revision = ("6f32d7549a9a", "2cc4e7d820a6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "store_quotes",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column(
            "contact_id", sa.Integer(), sa.ForeignKey("contacts.id"), nullable=False
        ),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("store_customers.id"),
            nullable=False,
        ),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("order_result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_store_quotes_contact_id", "store_quotes", ["contact_id"])
    op.create_index("ix_store_quotes_customer_id", "store_quotes", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_store_quotes_customer_id", table_name="store_quotes")
    op.drop_index("ix_store_quotes_contact_id", table_name="store_quotes")
    op.drop_table("store_quotes")
