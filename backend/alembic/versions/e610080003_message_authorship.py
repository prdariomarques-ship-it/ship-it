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
    # Review finding: column existence alone does not prove THIS migration
    # created it. On the real production database (darioos_cutover_20260927)
    # these three columns, with real historical data, already existed
    # before this migration's upgrade() ever ran there -- upgrade() was a
    # pure no-op catch-up (see module docstring). A downgrade that drops
    # "whatever exists" would silently destroy that real authorship/
    # instance history, not just undo what this migration actually built.
    #
    # The one thing we CAN check reliably: whether there is any real data
    # in these columns. A fresh database where upgrade() just created them
    # has none yet, and reverting there is genuinely safe. A database
    # where they already carry real values -- production, or any copy of
    # it -- must refuse, full stop. 002's own safeguards do not cover this:
    # they protect against OTHER data loss, not a 003-to-002 reversal.
    bind = op.get_bind()
    existing_columns = {c['name'] for c in sa.inspect(bind).get_columns('messages')}
    target_columns = {'sent_by_human', 'is_autopilot_reply', 'whatsapp_instance'} & existing_columns
    if not target_columns:
        return  # nothing to drop -- already absent

    has_real_data = bind.execute(sa.text(
        "SELECT 1 FROM messages WHERE sent_by_human IS TRUE "
        "OR is_autopilot_reply IS TRUE OR whatsapp_instance IS NOT NULL LIMIT 1"
    )).first()
    if has_real_data is not None:
        raise RuntimeError(
            "Refusing to downgrade e610080003: messages.sent_by_human / "
            "is_autopilot_reply / whatsapp_instance contain real data. "
            "Their existence does not prove this migration created them -- "
            "on production they pre-existed this migration's upgrade() "
            "entirely (a no-op there). Dropping them now would destroy "
            "real authorship/instance history this migration never "
            "created. To go back past this point, restore from a tested "
            "backup taken before that decision -- do not run this "
            "downgrade against a database that has ever processed real "
            "messages."
        )

    existing_indexes = {ix['name'] for ix in sa.inspect(bind).get_indexes('messages')}
    if 'ix_messages_whatsapp_instance' in existing_indexes:
        op.drop_index('ix_messages_whatsapp_instance', table_name='messages')
    with op.batch_alter_table('messages') as batch:
        for column_name in ('whatsapp_instance', 'is_autopilot_reply', 'sent_by_human'):
            if column_name in existing_columns:
                batch.drop_column(column_name)
