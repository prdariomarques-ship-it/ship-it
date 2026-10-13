"""Digital twin: pending-reply marker on contacts, human/autopilot flags on messages."""

from alembic import op
import sqlalchemy as sa

revision = "c91d5e7a3b20"
down_revision = "b82f0194de63"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "contacts",
        sa.Column("awaiting_reply_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column(
            "sent_by_human", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "messages",
        sa.Column(
            "is_autopilot_reply",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("messages", "is_autopilot_reply")
    op.drop_column("messages", "sent_by_human")
    op.drop_column("contacts", "awaiting_reply_since")
