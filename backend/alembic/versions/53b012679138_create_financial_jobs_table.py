"""create financial_jobs table (isolated from jobs)

Revision ID: 53b012679138
Revises: 86ec0249ba12
Create Date: 2026-10-06 00:00:00.000000

NOT APPLIED to any environment as of this commit — prepared for review
only, per the explicit hold on migrations against the live database
until a deployment window is agreed.

Purely additive: one new table, no change to any existing table
(including `jobs`). A downgrade only drops this table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "53b012679138"
down_revision: Union[str, None] = "86ec0249ba12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "financial_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", name="financialjobstatus"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_financial_jobs_name", "financial_jobs", ["name"])
    op.create_index("ix_financial_jobs_status", "financial_jobs", ["status"])
    op.create_index("ix_financial_jobs_scheduled_at", "financial_jobs", ["scheduled_at"])
    # Scoped to the three self-rescheduling chain names only — NOT to
    # telegram.send_message, which every feed shares as its job name and
    # must be free to have several independent rows pending at once.
    _chain_names = "('market.check_spcx34', 'market.send_b3_summary', 'market.send_daily_briefing')"
    op.create_index(
        "ix_financial_jobs_one_active_chain_per_name",
        "financial_jobs",
        ["name"],
        unique=True,
        postgresql_where=sa.text(f"status IN ('QUEUED', 'RUNNING') AND name IN {_chain_names}"),
        sqlite_where=sa.text(f"status IN ('QUEUED', 'RUNNING') AND name IN {_chain_names}"),
    )


def downgrade() -> None:
    op.drop_table("financial_jobs")
    op.execute("DROP TYPE IF EXISTS financialjobstatus")
