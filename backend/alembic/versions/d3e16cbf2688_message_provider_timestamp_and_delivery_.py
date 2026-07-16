"""message provider_timestamp and delivery_status

Revision ID: d3e16cbf2688
Revises: abb2a2bf950e
Create Date: 2026-07-10 02:05:17.940488

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d3e16cbf2688"
down_revision: Union[str, None] = "abb2a2bf950e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# `op.add_column` performs a plain ALTER TABLE, which never goes through the
# CREATE-TABLE DDL event chain that normally auto-creates a PG enum type
# (that's how the enums in 790826c45a84_initial_schema.py got created — they
# were columns on op.create_table(...), not op.add_column(...)). The type
# has to be created explicitly here; `create_type=False` stops SQLAlchemy
# from also trying to implicitly create/drop it when the column DDL runs.
_delivery_status_enum = postgresql.ENUM(
    "SENT",
    "DELIVERED",
    "READ",
    "FAILED",
    name="messagedeliverystatus",
    create_type=False,
)


def upgrade() -> None:
    _delivery_status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "messages",
        sa.Column("provider_timestamp", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "messages", sa.Column("delivery_status", _delivery_status_enum, nullable=True)
    )


def downgrade() -> None:
    op.drop_column("messages", "delivery_status")
    op.drop_column("messages", "provider_timestamp")
    _delivery_status_enum.drop(op.get_bind(), checkfirst=True)
