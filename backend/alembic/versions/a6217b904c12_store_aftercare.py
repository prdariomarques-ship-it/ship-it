"""Delivery-confirmed follow-up and contact-scoped support cases."""

from alembic import op
import sqlalchemy as sa

revision = "a6217b904c12"
down_revision = "f4c18a2d9e10"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(name, sa.DateTime(timezone=True), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def upgrade():
    op.create_table(
        "store_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("store_customers.id"),
            nullable=False,
        ),
        sa.Column(
            "contact_id", sa.Integer(), sa.ForeignKey("contacts.id"), nullable=False
        ),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("followup_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("detail", sa.Text()),
        sa.Column(
            "confirmed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        *timestamps(),
        sa.UniqueConstraint("customer_id", "order_id"),
    )
    op.create_index(
        "ix_store_deliveries_contact_id", "store_deliveries", ["contact_id"]
    )
    op.create_table(
        "store_support_cases",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column(
            "contact_id", sa.Integer(), sa.ForeignKey("contacts.id"), nullable=False
        ),
        sa.Column(
            "source_message_id", sa.Integer(), sa.ForeignKey("messages.id"), unique=True
        ),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("report", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("resolution", sa.Text()),
        *timestamps(),
    )
    op.create_index(
        "ix_store_support_cases_contact_id", "store_support_cases", ["contact_id"]
    )


def downgrade():
    op.drop_table("store_support_cases")
    op.drop_table("store_deliveries")
