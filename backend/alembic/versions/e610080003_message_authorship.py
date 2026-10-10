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

# Review fix (round 2 of the downgrade-safety finding): a database-level
# marker, not an inference from column values, is the only reliable proof
# that THIS migration's upgrade() -- in THIS database -- is what created
# messages.sent_by_human / is_autopilot_reply / whatsapp_instance. The
# previous check ("do any rows have non-default values?") missed a real
# case: a pre-existing, non-empty messages table whose authorship columns
# happen to carry only FALSE/FALSE/NULL (e.g. a freshly-migrated-but-
# unused environment, or simply no owner reply or autopilot send has
# happened yet) looked "safe to drop" under that check even though this
# migration never created those columns there. The marker table is only
# ever written inside the branch that actually adds a column that was
# previously absent -- the no-op branch (columns already present, as on
# real production) never writes it, so downgrade() has unambiguous proof
# either way instead of a data-shaped guess.
_MARKER_TABLE = '_mig_e610080003_created_authorship_columns'


def upgrade():
    bind = op.get_bind()
    existing_columns = {c['name'] for c in sa.inspect(bind).get_columns('messages')}
    columns_to_add = {'sent_by_human', 'is_autopilot_reply', 'whatsapp_instance'} - existing_columns
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

    if columns_to_add and not sa.inspect(bind).has_table(_MARKER_TABLE):
        op.create_table(
            _MARKER_TABLE,
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.execute(sa.text(f'INSERT INTO "{_MARKER_TABLE}" DEFAULT VALUES'))


def downgrade():
    # Review finding: column existence alone does not prove THIS migration
    # created it. On the real production database (darioos_cutover_20260927)
    # these three columns, with real historical data, already existed
    # before this migration's upgrade() ever ran there -- upgrade() was a
    # pure no-op catch-up (see module docstring). A downgrade that drops
    # "whatever exists" would silently destroy that real authorship/
    # instance history, not just undo what this migration actually built.
    #
    # Review fix (round 2): a data-value check alone ("are they all still
    # FALSE/FALSE/NULL?") is not proof of ownership either -- a pre-
    # existing, non-empty messages table can carry exactly those defaults
    # without this migration ever having touched it. The ONLY reliable
    # proof is the marker table upgrade() writes, and only in the branch
    # where it actually added a column that was previously absent. Both
    # checks below must pass: ownership (the marker) AND no real data has
    # accumulated since (the original data check, kept as a second,
    # independent guard -- even a database this migration legitimately
    # created the columns in should not have its real authorship history
    # silently dropped by an operator deciding to roll back later).
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {c['name'] for c in inspector.get_columns('messages')}
    target_columns = {'sent_by_human', 'is_autopilot_reply', 'whatsapp_instance'} & existing_columns
    if not target_columns:
        return  # nothing to drop -- already absent

    if not inspector.has_table(_MARKER_TABLE):
        raise RuntimeError(
            "Refusing to downgrade e610080003: there is no reliable record "
            "(the upgrade-time marker table) proving THIS migration's "
            "upgrade() created messages.sent_by_human / is_autopilot_reply "
            "/ whatsapp_instance in this database. Column existence, or "
            "all-default values, do not prove that -- on production these "
            "columns pre-existed this migration's upgrade() entirely (a "
            "no-op there), and a pre-existing, non-empty table can carry "
            "nothing but FALSE/FALSE/NULL in them with no relation to this "
            "migration at all. Dropping them now could destroy a pre-"
            "existing production baseline this migration never created. "
            "To go back past this point, restore from a tested backup "
            "taken before that decision."
        )

    has_real_data = bind.execute(sa.text(
        "SELECT 1 FROM messages WHERE sent_by_human IS TRUE "
        "OR is_autopilot_reply IS TRUE OR whatsapp_instance IS NOT NULL LIMIT 1"
    )).first()
    if has_real_data is not None:
        raise RuntimeError(
            "Refusing to downgrade e610080003: messages.sent_by_human / "
            "is_autopilot_reply / whatsapp_instance contain real data, "
            "even though this migration's own upgrade() created them in "
            "this database. Dropping them now would destroy real "
            "authorship/instance history that has accumulated since. To "
            "go back past this point, restore from a tested backup taken "
            "before that decision."
        )

    existing_indexes = {ix['name'] for ix in inspector.get_indexes('messages')}
    if 'ix_messages_whatsapp_instance' in existing_indexes:
        op.drop_index('ix_messages_whatsapp_instance', table_name='messages')
    with op.batch_alter_table('messages') as batch:
        for column_name in ('whatsapp_instance', 'is_autopilot_reply', 'sent_by_human'):
            if column_name in existing_columns:
                batch.drop_column(column_name)
    op.drop_table(_MARKER_TABLE)
