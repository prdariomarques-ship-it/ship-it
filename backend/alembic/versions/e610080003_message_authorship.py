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
import alembic.op as op
import sqlalchemy as sa

revision = 'e610080003'
down_revision = 'e610080002'
branch_labels = None
depends_on = None

# Review fix (round 5 of the downgrade-safety finding): the previous marker
# was a single GLOBAL flag ("upgrade() created *something* here") -- that
# let creating just ONE missing object (say, only whatsapp_instance was
# absent while sent_by_human/is_autopilot_reply pre-existed with real data)
# authorize downgrade() to drop ALL THREE, including the two it never
# created. This version tracks ownership PER OBJECT: one row per column/
# index name, written only for the specific objects THIS call of upgrade()
# actually created. upgrade() always ensures this table exists once it has
# run here at all (even if it creates zero objects, i.e. the full
# production no-op case) -- that is what lets downgrade() tell "upgrade
# ran here and genuinely found everything pre-existing" (marker table
# exists, empty/missing rows for the pre-existing objects -- safe to leave
# them alone, no error) apart from "upgrade() never ran against this
# database at all" (marker table absent entirely -- unresolvable, must
# refuse rather than guess).
_MARKER_TABLE = '_mig_e610080003_created_objects'
# The OLD, global-flag marker from the previous version of this migration.
# If this exists, some earlier run already executed the old upgrade()
# logic -- its single row proves only "something was created", never WHICH
# column(s)/index, so it cannot be reinterpreted under the new per-object
# scheme without inventing provenance this migration never actually
# recorded. downgrade() must recognize and refuse on sight, not migrate or
# reuse its meaning.
_LEGACY_MARKER_TABLE = '_mig_e610080003_created_authorship_columns'

_TRACKED_COLUMNS = ('sent_by_human', 'is_autopilot_reply', 'whatsapp_instance')
_INDEX_NAME = 'ix_messages_whatsapp_instance'


def _ensure_marker_table(bind) -> None:
    if not sa.inspect(bind).has_table(_MARKER_TABLE):
        op.create_table(
            _MARKER_TABLE,
            sa.Column('object_name', sa.String(128), primary_key=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def _record_created(bind, object_name: str) -> None:
    bind.execute(
        sa.text(f'INSERT INTO "{_MARKER_TABLE}" (object_name) VALUES (:name)'),
        {'name': object_name},
    )


def upgrade():
    bind = op.get_bind()
    existing_columns = {c['name'] for c in sa.inspect(bind).get_columns('messages')}
    existing_indexes = {ix['name'] for ix in sa.inspect(bind).get_indexes('messages')}

    created: list[str] = []
    with op.batch_alter_table('messages') as batch:
        if 'sent_by_human' not in existing_columns:
            batch.add_column(sa.Column('sent_by_human', sa.Boolean(), nullable=False,
                                        server_default=sa.false()))
            created.append('sent_by_human')
        if 'is_autopilot_reply' not in existing_columns:
            batch.add_column(sa.Column('is_autopilot_reply', sa.Boolean(), nullable=False,
                                        server_default=sa.false()))
            created.append('is_autopilot_reply')
        if 'whatsapp_instance' not in existing_columns:
            batch.add_column(sa.Column('whatsapp_instance', sa.String(128), nullable=True))
            created.append('whatsapp_instance')

    if _INDEX_NAME not in existing_indexes:
        op.create_index(_INDEX_NAME, 'messages', ['whatsapp_instance'])
        created.append(_INDEX_NAME)

    # Always ensure the marker table exists once upgrade() has run here at
    # all -- even with zero rows (every tracked object pre-existed, as on
    # real production) -- so downgrade() can tell that apart from upgrade()
    # never having run against this database in the first place.
    _ensure_marker_table(bind)
    for name in created:
        _record_created(bind, name)


def downgrade():
    # Review finding (round 5): "did this migration create *something*
    # here" is not the right question -- it must be "did this migration
    # create *this specific* column/index here", object by object, or a
    # database with even one genuinely pre-existing authorship column (real
    # production: all three pre-exist) gets ALL of them dropped the moment
    # any ONE object happens to be missing and gets created. The per-object
    # marker table (populated only by upgrade(), only for what it actually
    # created) is the only reliable source -- never column/table emptiness
    # or FALSE/FALSE/NULL defaults, which a genuinely foreign, pre-existing,
    # merely-unused column can show just as easily as one we created.
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table(_LEGACY_MARKER_TABLE):
        raise RuntimeError(
            f'Refusing to downgrade e610080003: found "{_LEGACY_MARKER_TABLE}", '
            "the OLD global-flag marker from an earlier version of this "
            "migration. That marker only recorded that upgrade() created "
            "SOMETHING here, never which specific column(s)/index -- reusing "
            "it under the current per-object ownership scheme would mean "
            "inventing provenance this migration never actually recorded. "
            "Resolve this by hand: inspect messages.sent_by_human / "
            "is_autopilot_reply / whatsapp_instance and ix_messages_"
            "whatsapp_instance directly against this database before "
            "deciding what, if anything, is safe to remove."
        )

    existing_columns = {c['name'] for c in inspector.get_columns('messages')}
    existing_indexes = {ix['name'] for ix in inspector.get_indexes('messages')}
    present_columns = set(_TRACKED_COLUMNS) & existing_columns
    index_present = _INDEX_NAME in existing_indexes

    if not present_columns and not index_present:
        return  # nothing of ours could possibly still be here

    if not inspector.has_table(_MARKER_TABLE):
        # upgrade() never ran against this database at all -- there is no
        # record of what, if anything, it evaluated here. Column/index
        # presence alone proves nothing about who put them there.
        raise RuntimeError(
            "Refusing to downgrade e610080003: messages.sent_by_human / "
            "is_autopilot_reply / whatsapp_instance (and/or "
            f"{_INDEX_NAME}) are present, but there is no record "
            f'("{_MARKER_TABLE}") that this migration'"'"'s own upgrade() '
            "ever ran against this database, let alone which objects it "
            "created here. Their existence does not prove this migration "
            "owns them -- on production they pre-existed this migration's "
            "upgrade() entirely. To go back past this point, restore from "
            "a tested backup taken before that decision, or confirm "
            "manually that every one of these objects is safe to drop and "
            "remove them by hand."
        )

    owned = {
        row[0] for row in bind.execute(sa.text(f'SELECT object_name FROM "{_MARKER_TABLE}"'))
    }

    def _has_real_data(predicate: str) -> bool:
        return bind.execute(sa.text(f"SELECT 1 FROM messages WHERE {predicate} LIMIT 1")).first() is not None

    index_owned = index_present and _INDEX_NAME in owned

    # Objects NOT in `owned` are proven foreign (upgrade() looked at every
    # tracked name explicitly and chose not to create them because they
    # already existed) -- always left alone, never even considered below.
    blocked: list[str] = []
    columns_to_drop: list[str] = []

    for column, predicate in (
        ('sent_by_human', 'sent_by_human IS TRUE'),
        ('is_autopilot_reply', 'is_autopilot_reply IS TRUE'),
    ):
        if column in present_columns and column in owned:
            if _has_real_data(predicate):
                blocked.append(column)
            else:
                columns_to_drop.append(column)

    if 'whatsapp_instance' in present_columns and 'whatsapp_instance' in owned:
        if _has_real_data('whatsapp_instance IS NOT NULL'):
            blocked.append('whatsapp_instance')
        elif index_present and not index_owned:
            # Dropping this column would force the database to drop the
            # index on it as a side effect -- but that index is NOT ours
            # (it pre-existed independently of this migration's upgrade()).
            # Destroying someone else's index just because we own the
            # column it happens to sit on is exactly the kind of foreign-
            # object removal this fix exists to prevent.
            blocked.append('whatsapp_instance (coupled to a foreign index)')
        else:
            columns_to_drop.append('whatsapp_instance')

    if blocked:
        raise RuntimeError(
            "Refusing to downgrade e610080003: " + ", ".join(blocked) + " "
            "-- created by this migration's own upgrade() in this database, "
            "but either carrying real data that would be destroyed, or "
            "coupled to an index this migration does not own. Objects this "
            "migration never created are left untouched regardless; "
            "resolve the blocked object(s) by hand (restore from a tested "
            "backup, or confirm manually that the data/index in question is "
            "disposable) before retrying."
        )

    drop_index_now = index_owned
    if drop_index_now:
        op.drop_index(_INDEX_NAME, table_name='messages')
    if columns_to_drop:
        with op.batch_alter_table('messages') as batch:
            for column_name in columns_to_drop:
                batch.drop_column(column_name)

    removed = set(columns_to_drop) | ({_INDEX_NAME} if drop_index_now else set())
    if removed:
        for name in removed:
            bind.execute(sa.text(f'DELETE FROM "{_MARKER_TABLE}" WHERE object_name = :name'), {'name': name})
        if bind.execute(sa.text(f'SELECT 1 FROM "{_MARKER_TABLE}" LIMIT 1')).first() is None:
            op.drop_table(_MARKER_TABLE)
