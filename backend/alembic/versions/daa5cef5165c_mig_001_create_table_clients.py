"""MIG-001: Create table clients

Revision ID: daa5cef5165c
Revises: 0e6459491047
Create Date: 2026-07-12 16:32:38.499005

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "daa5cef5165c"
down_revision: Union[str, None] = "0e6459491047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.BIGINT(), nullable=False, autoincrement=True),
        sa.Column("name", sa.VARCHAR(length=255), nullable=False),
        sa.Column("email", sa.VARCHAR(length=255), nullable=False),
        sa.Column("phone", sa.VARCHAR(length=20), nullable=True),
        sa.Column("address", sa.JSON(), nullable=True),
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
        sa.UniqueConstraint("email", name="clients_email_unique"),
    )
    op.create_index("clients_created_at_idx", "clients", ["created_at"])


def downgrade() -> None:
    op.drop_index("clients_created_at_idx", table_name="clients")
    op.drop_table("clients")
