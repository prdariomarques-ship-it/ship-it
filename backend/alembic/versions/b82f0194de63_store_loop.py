"""Persistent customer objectives and explicit corrections."""

from alembic import op
import sqlalchemy as sa

revision = "b82f0194de63"
down_revision = "a6217b904c12"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(n, sa.DateTime(timezone=True), nullable=False)
        for n in ("created_at", "updated_at")
    ]


def upgrade():
    op.create_table(
        "store_loop_goals",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column(
            "contact_id", sa.Integer(), sa.ForeignKey("contacts.id"), nullable=False
        ),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("objective", sa.String(300), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("next_step", sa.String(400), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("evidence_id", sa.String(64)),
        *timestamps(),
    )
    op.create_index(
        "ix_store_loop_goals_contact_id", "store_loop_goals", ["contact_id"]
    )
    op.create_table(
        "store_corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "contact_id", sa.Integer(), sa.ForeignKey("contacts.id"), nullable=False
        ),
        sa.Column("field", sa.String(40), nullable=False),
        sa.Column("value", sa.String(200), nullable=False),
        sa.Column("source_excerpt", sa.String(1000), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("contact_id", "field"),
    )
    op.create_index(
        "ix_store_corrections_contact_id", "store_corrections", ["contact_id"]
    )


def downgrade():
    op.drop_table("store_corrections")
    op.drop_table("store_loop_goals")
