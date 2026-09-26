"""Merge heads: tasks/calendar contact_id and products/store

Revision ID: b7e2c91f4a60
Revises: 2cc4e7d820a6, 6f32d7549a9a
Create Date: 2026-09-26 00:00:00.000000

"""

from typing import Sequence, Union


revision: str = "b7e2c91f4a60"
down_revision: Union[str, Sequence[str], None] = ("2cc4e7d820a6", "6f32d7549a9a")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
