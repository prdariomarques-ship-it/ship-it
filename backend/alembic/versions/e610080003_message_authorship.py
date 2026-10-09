"""Message authorship/instance columns the review found jobs/handlers.py and
webhooks/router.py already depend on (sent_by_human, is_autopilot_reply,
whatsapp_instance) but that had no migration in this repository's history.

Confirmed via \\d messages against the real production database
(darioos_cutover_20260927, alembic head 9e2f1c6d7a80) that these columns
already exist there -- some earlier migration added them that never made it
into this repository (same class of gap as handlers.py/router.py's missing
baseline). This migration is therefore written to be a safe no-op against
that already-correct production schema (checked via column introspection,
not assumed), while still actually creating the columns for a fresh test
database built from this migration chain (SQLite, as the review's own
test harness does).

Revision ID: e610080003
Revises: e610080002
"""
from alembic import op
import sqlalchemy as sa

revision = 'e610080003'
down_revision = 'e610080002'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing_columns = {c['name'] for c in sa.inspect(bind).get_columns('messages')}
    with op.batch_alter_table('messages') as batch:
        if 'sent_by_human' not in existing_columns:
            batch.add_column(sa.Column('sent_by_human', sa.Boolean(), nullable=False,
                                        server_default=sa.false()))
        if 'is_autopilot_reply' not in existing_columns:
            batch.add_column(sa.Column('is_autopilot_reply', sa.Boolean(), nullable=False,
                                        server_default=sa.false()))
        if 'whatsapp_instance' not in existing_columns:
            batch.add_column(sa.Column('whatsapp_instance', sa.String(128), nullable=True))
    existing_indexes = {ix['name'] for ix in sa.inspect(bind).get_indexes('messages')}
    if 'ix_messages_whatsapp_instance' not in existing_indexes:
        op.create_index('ix_messages_whatsapp_instance', 'messages', ['whatsapp_instance'])


def downgrade():
    bind = op.get_bind()
    existing_indexes = {ix['name'] for ix in sa.inspect(bind).get_indexes('messages')}
    if 'ix_messages_whatsapp_instance' in existing_indexes:
        op.drop_index('ix_messages_whatsapp_instance', table_name='messages')
    existing_columns = {c['name'] for c in sa.inspect(bind).get_columns('messages')}
    with op.batch_alter_table('messages') as batch:
        if 'whatsapp_instance' in existing_columns:
            batch.drop_column('whatsapp_instance')
        if 'is_autopilot_reply' in existing_columns:
            batch.drop_column('is_autopilot_reply')
        if 'sent_by_human' in existing_columns:
            batch.drop_column('sent_by_human')
