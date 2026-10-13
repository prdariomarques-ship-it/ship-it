"""Scope WhatsApp messages by Evolution instance."""

from alembic import op
import sqlalchemy as sa

revision = "7d31a9b4e2c1"
down_revision = "51081d0451d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "whatsapp_instance",
            sa.String(length=128),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_messages_whatsapp_instance",
        "messages",
        ["whatsapp_instance"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_messages_whatsapp_instance",
        table_name="messages",
    )
    op.drop_column("messages", "whatsapp_instance")
