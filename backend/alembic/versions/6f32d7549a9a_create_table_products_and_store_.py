"""Create table products and add store_customers.segment

Revision ID: 6f32d7549a9a
Revises: a1f9c3d84e2b
Create Date: 2026-09-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6f32d7549a9a"
down_revision: Union[str, None] = "a1f9c3d84e2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_sku"), "products", ["sku"], unique=True)
    op.create_index(op.f("ix_products_category"), "products", ["category"], unique=False)

    op.add_column(
        "store_customers", sa.Column("segment", sa.String(length=50), nullable=True)
    )
    op.create_index(
        op.f("ix_store_customers_segment"), "store_customers", ["segment"], unique=False
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_store_customers_segment"), table_name="store_customers"
    )
    op.drop_column("store_customers", "segment")

    op.drop_index(op.f("ix_products_category"), table_name="products")
    op.drop_index(op.f("ix_products_sku"), table_name="products")
    op.drop_table("products")
