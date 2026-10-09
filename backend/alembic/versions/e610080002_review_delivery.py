"""Explicitly close uncertain delivery without asserting remote non-delivery.

Revision ID: e610080002
Revises: e610080001
Legacy and crashed transports default unfinished and cannot be closed.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e610080002'
down_revision = 'e610080001'
branch_labels = None
depends_on = None


def upgrade():
    for table, check, statuses in (
        ('conversation_send_intents', 'ck_send_status', "'suppressed','needs_review','sent','closed_unknown'"),
        ('conversation_alert_intents', 'ck_alert_status', "'pending','needs_review','sent','closed_unknown'"),
    ):
        # Batch mode rebuilds SQLite tables, preserving checks, keys and indexes;
        # PostgreSQL uses ordinary ALTER TABLE under the same migration.
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('transport_finished', sa.Boolean(), nullable=False,
                                       server_default=sa.false()))
            batch.drop_constraint(check, type_='check')
            batch.create_check_constraint(check, f'status IN ({statuses})')
    with op.batch_alter_table('conversation_control_audit') as batch:
        batch.add_column(sa.Column('prior_revision', sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column('intent_kind', sa.String(16), nullable=True))
        batch.add_column(sa.Column('intent_key', sa.String(255), nullable=True))


def downgrade():
    raise RuntimeError('Delivery review migration cannot be downgraded: closed outcomes and audit history must be preserved')
