"""Real PostgreSQL 16 (local to this sandbox), proving e610080003's
upgrade/downgrade behavior against the full scenario matrix the review
asked for -- not just read as source, actually run against a real
database.

Review fix (round 5): the marker table that proves ownership used to be a
single GLOBAL flag ("upgrade() created *something* in this database") --
that let creating just ONE missing object (e.g. only `whatsapp_instance`
was absent while `sent_by_human`/`is_autopilot_reply` pre-existed with
real data) authorize downgrade() to drop ALL THREE objects, including the
two it never created. The migration now tracks ownership PER OBJECT (one
marker row per column/index name, written only for what THAT call of
upgrade() actually created), and downgrade() only ever removes objects it
can prove, object by object, that it created -- never inferring from
column/table emptiness or FALSE/FALSE/NULL defaults, and never reusing the
OLD global marker's meaning if it's ever found.

Scenarios covered:
  1. No columns pre-exist at all: upgrade() creates all three + the index,
     owning every one of them (marker row per object).
  2. All three (and the index) pre-exist with real historical data (the
     real production shape): upgrade() is a true no-op, and still records
     (empty) that it ran here, owning nothing.
  2b/2c. Following on from 2 -- downgrade() after that real upgrade() run
     succeeds as a clean NO-OP (owns nothing, so it removes nothing) on
     BOTH a fully pre-existing real-data environment and a fully
     pre-existing default-only one. Column/table emptiness and FALSE/
     FALSE/NULL values are never read as proof of ownership in either
     direction -- they don't grant it, and they don't block a no-op either.
  3/4. All pre-exist, but upgrade() was NEVER actually run against this
     database at all (synthetic: alembic's own tracking was bypassed) --
     no marker table whatsoever -- downgrade refuses in BOTH the real-data
     and default-only cases, since there is no record of what, if
     anything, was evaluated here.
  5/6. Everything is owned (upgrade() created it): downgrade succeeds on
     an empty table AND on a non-empty table whose owned columns carry
     only default values -- proving the block is about ownership+data,
     not a blanket refusal to ever downgrade.
  7. An owned column later accumulates real data: downgrade refuses,
     naming that specific column, even though ownership is proven.
  8. Only SOME columns pre-exist: downgrade removes only the ones this
     migration actually created, leaving the pre-existing column and its
     real data completely untouched.
  9. The index is absent while its column pre-exists: upgrade() owns only
     the index; downgrade drops only the index, leaving the (foreign)
     column and its data alone.
  10. Defensive-only path: the index's ownership record is missing (by
      tampering, since a pre-existing index without its column is not
      constructible in SQL) while the column's IS owned -- downgrade must
      refuse rather than force-drop a column and silently take a foreign
      index down with it.
  11. The OLD, global-flag marker from a previous version of this
      migration is present: downgrade refuses outright, never reinterprets
      it under the new per-object scheme.

Opt-in only, same pattern as test_dedup_key_postgresql_isolated.py: set
WHATSAPP_DEDUP_PG_ADMIN_URL before running; without it, every test here is
skipped, not run against any guessed or default credential.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

HERE = Path(__file__).parent
BACKEND_ROOT = HERE.parents[0]

ADMIN_URL = os.environ.get("WHATSAPP_DEDUP_PG_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not ADMIN_URL,
    reason="WHATSAPP_DEDUP_PG_ADMIN_URL not set -- no PostgreSQL admin connection configured, skipping real-Postgres tests",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "mig_e610080003", BACKEND_ROOT / "alembic" / "versions" / "e610080003_message_authorship.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _db_url(dbname: str) -> str:
    return make_url(ADMIN_URL).set(database=dbname).render_as_string(hide_password=False)


async def _create_database(dbname: str) -> None:
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    await admin.dispose()


async def _drop_database(dbname: str) -> None:
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{dbname}' AND pid <> pg_backend_pid()"
        ))
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}"'))
    await admin.dispose()


@pytest.fixture
async def isolated_db():
    dbname = f"whatsapp_authorship_mig_{uuid.uuid4().hex[:12]}"
    try:
        await _create_database(dbname)
    except Exception:
        await _drop_database(dbname)
        raise
    try:
        yield dbname
    finally:
        await _drop_database(dbname)


def _run_sync_migration(sync_conn, fn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(sync_conn)
    with Operations.context(ctx):
        fn()


async def _columns(conn):
    return {row[0] for row in (await conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='messages'"
    ))).fetchall()}


async def _indexes(conn):
    return {row[0] for row in (await conn.execute(text(
        "SELECT indexname FROM pg_indexes WHERE tablename='messages'"
    ))).fetchall()}


async def _marker_rows(conn, table="_mig_e610080003_created_objects"):
    exists = (await conn.execute(text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
    ), {"t": table})).first()
    if exists is None:
        return None
    return {row[0] for row in (await conn.execute(text(f'SELECT object_name FROM "{table}"'))).fetchall()}


@pytest.mark.asyncio
async def test_upgrade_adds_all_three_columns_and_index_and_owns_all_of_them(isolated_db):
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "contact_id integer, direction varchar(16))"
            ))
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.upgrade))
        async with engine.connect() as conn:
            cols = await _columns(conn)
            idx = await _indexes(conn)
            owned = await _marker_rows(conn)
        assert {"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} <= cols
        assert "ix_messages_whatsapp_instance" in idx
        assert owned == {"sent_by_human", "is_autopilot_reply", "whatsapp_instance", "ix_messages_whatsapp_instance"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_upgrade_is_a_true_noop_and_owns_nothing_when_everything_preexists(isolated_db):
    """The real production scenario: columns (and the index) with real
    historical data already there BEFORE this migration's upgrade() ever
    runs. Must not touch data, and must record that it ran here while
    owning zero objects -- not the same as never having run at all."""
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "contact_id integer, direction varchar(16), "
                "sent_by_human boolean not null default false, "
                "is_autopilot_reply boolean not null default false, "
                "whatsapp_instance varchar(128))"
            ))
            await conn.execute(text("CREATE INDEX ix_messages_whatsapp_instance ON messages (whatsapp_instance)"))
            await conn.execute(text(
                "INSERT INTO messages (content, sent_by_human, is_autopilot_reply, whatsapp_instance) "
                "VALUES ('resposta real do dono', true, false, 'dario'), "
                "('resposta automatica real', false, true, 'azusa-church')"
            ))
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.upgrade))  # must not raise

        async with engine.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT content, sent_by_human, is_autopilot_reply, whatsapp_instance "
                "FROM messages ORDER BY id"
            ))).fetchall()
            owned = await _marker_rows(conn)
        assert len(rows) == 2
        assert rows[0] == ("resposta real do dono", True, False, "dario")
        assert rows[1] == ("resposta automatica real", False, True, "azusa-church")
        assert owned == set()  # upgrade() ran here, but created and owns nothing
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_refuses_when_upgrade_never_ran_here_and_real_data_is_present(isolated_db):
    """The scenario the review flagged: a database that has processed real
    messages must never have this data silently dropped by a 003->002
    downgrade. No marker table at all -- upgrade() never ran here."""
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "sent_by_human boolean not null default false, "
                "is_autopilot_reply boolean not null default false, "
                "whatsapp_instance varchar(128))"
            ))
            await conn.execute(text(
                "INSERT INTO messages (content, sent_by_human, whatsapp_instance) "
                "VALUES ('historico real do proprietario', true, 'dario')"
            ))

        with pytest.raises(Exception):
            async with engine.begin() as conn:
                await conn.run_sync(lambda c: _run_sync_migration(c, migration.downgrade))

        # The failed transaction must not have committed any partial
        # DROP COLUMN -- verify the columns and the real row are still
        # there, not just that an exception surfaced.
        async with engine.connect() as conn:
            cols = await _columns(conn)
            row = (await conn.execute(text(
                "SELECT content, sent_by_human, whatsapp_instance FROM messages"
            ))).fetchone()
        assert {"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} <= cols
        assert row == ("historico real do proprietario", True, "dario")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_refuses_when_upgrade_never_ran_here_and_values_are_only_defaults(isolated_db):
    """Same as the real-data variant above, but with only default values --
    column/table emptiness and FALSE/FALSE/NULL must never be read as
    proof of ownership EITHER way. upgrade() is never called at all here
    (alembic's own tracking bypassed, synthetic) -- no marker table
    whatsoever -- must still refuse."""
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "sent_by_human boolean not null default false, "
                "is_autopilot_reply boolean not null default false, "
                "whatsapp_instance varchar(128))"
            ))
            await conn.execute(text(
                "INSERT INTO messages (content) VALUES "
                "('mensagem anterior a esta migracao'), "
                "('outra mensagem anterior, sem autoria registrada')"
            ))

        with pytest.raises(Exception):
            async with engine.begin() as conn:
                await conn.run_sync(lambda c: _run_sync_migration(c, migration.downgrade))

        async with engine.connect() as conn:
            cols = await _columns(conn)
            rows = (await conn.execute(text("SELECT content FROM messages ORDER BY id"))).fetchall()
        assert {"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} <= cols
        assert len(rows) == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_is_a_clean_noop_after_a_real_upgrade_run_against_a_fully_preexisting_default_only_environment(isolated_db):
    """The real production shape, end to end: columns and the index all
    pre-exist (upgrade() genuinely runs here and owns nothing, as in
    test_upgrade_is_a_true_noop... above), values are only defaults --
    downgrade must succeed as a clean no-op, removing nothing, since
    nothing is owned. Not a refusal: there is nothing unsafe happening,
    there is simply nothing of this migration's own to revert."""
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "sent_by_human boolean not null default false, "
                "is_autopilot_reply boolean not null default false, "
                "whatsapp_instance varchar(128))"
            ))
            await conn.execute(text("CREATE INDEX ix_messages_whatsapp_instance ON messages (whatsapp_instance)"))
            await conn.execute(text(
                "INSERT INTO messages (content) VALUES "
                "('mensagem anterior a esta migracao'), "
                "('outra mensagem anterior, sem autoria registrada')"
            ))
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.upgrade))  # no-op, owns nothing
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.downgrade))  # must not raise

        async with engine.connect() as conn:
            cols = await _columns(conn)
            idx = await _indexes(conn)
            rows = (await conn.execute(text("SELECT content FROM messages ORDER BY id"))).fetchall()
        # Nothing owned -- nothing removed, structure and data both intact.
        assert {"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} <= cols
        assert "ix_messages_whatsapp_instance" in idx
        assert len(rows) == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_is_a_clean_noop_after_a_real_upgrade_run_against_a_fully_preexisting_real_data_environment(isolated_db):
    """Same as above, but with real authorship/instance data already
    present -- proves the no-op isn't merely "safe because there's no
    data to lose", it's safe because nothing is owned, period. Real data
    in unowned columns is never even inspected."""
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "sent_by_human boolean not null default false, "
                "is_autopilot_reply boolean not null default false, "
                "whatsapp_instance varchar(128))"
            ))
            await conn.execute(text("CREATE INDEX ix_messages_whatsapp_instance ON messages (whatsapp_instance)"))
            await conn.execute(text(
                "INSERT INTO messages (content, sent_by_human, is_autopilot_reply, whatsapp_instance) "
                "VALUES ('resposta real do dono', true, false, 'dario')"
            ))
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.upgrade))  # no-op, owns nothing
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.downgrade))  # must not raise

        async with engine.connect() as conn:
            cols = await _columns(conn)
            idx = await _indexes(conn)
            row = (await conn.execute(text(
                "SELECT content, sent_by_human, is_autopilot_reply, whatsapp_instance FROM messages"
            ))).fetchone()
        assert {"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} <= cols
        assert "ix_messages_whatsapp_instance" in idx
        assert row == ("resposta real do dono", True, False, "dario")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_succeeds_on_an_empty_table_when_this_migration_owns_everything(isolated_db):
    """The genuinely safe case: a fresh database that just ran upgrade()
    and never processed a single message through these columns."""
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "contact_id integer, direction varchar(16))"
            ))
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.upgrade))
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.downgrade))

        async with engine.connect() as conn:
            cols = await _columns(conn)
            idx = await _indexes(conn)
            owned = await _marker_rows(conn)
        assert not ({"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} & cols)
        assert "ix_messages_whatsapp_instance" not in idx
        assert owned is None  # marker table itself is dropped once empty
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_succeeds_on_a_nonempty_table_with_only_default_values_when_this_migration_owns_everything(isolated_db):
    """Same as the empty-table case, but with real rows present whose
    owned columns carry only the defaults -- ownership is proven (THIS
    migration's own upgrade() created them here), and there is no real
    data to lose, so downgrade must still succeed cleanly."""
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "contact_id integer, direction varchar(16))"
            ))
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.upgrade))
            await conn.execute(text(
                "INSERT INTO messages (content) VALUES ('mensagem comum, sem autoria especial')"
            ))
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.downgrade))

        async with engine.connect() as conn:
            cols = await _columns(conn)
            rows = (await conn.execute(text("SELECT content FROM messages"))).fetchall()
        assert not ({"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} & cols)
        assert len(rows) == 1  # the row itself is never touched, only the columns
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_refuses_when_an_owned_column_later_carries_real_data(isolated_db):
    """Ownership alone is not enough: even a column THIS migration's own
    upgrade() created can accumulate real data afterward (a real owner
    reply, a real autopilot send) that must not be silently destroyed by
    a later downgrade."""
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "contact_id integer, direction varchar(16))"
            ))
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.upgrade))
            await conn.execute(text(
                "INSERT INTO messages (content, sent_by_human, whatsapp_instance) "
                "VALUES ('resposta real depois da migracao', true, 'dario')"
            ))

        with pytest.raises(Exception):
            async with engine.begin() as conn:
                await conn.run_sync(lambda c: _run_sync_migration(c, migration.downgrade))

        async with engine.connect() as conn:
            cols = await _columns(conn)
            row = (await conn.execute(text(
                "SELECT content, sent_by_human, whatsapp_instance FROM messages"
            ))).fetchone()
        assert {"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} <= cols
        assert row == ("resposta real depois da migracao", True, "dario")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_removes_only_the_columns_this_migration_created_leaving_a_preexisting_one_with_its_data_intact(isolated_db):
    """Review finding (round 5): the old global marker let creating just
    ONE missing column authorize dropping ALL three. Here `whatsapp_instance`
    pre-exists with real historical data (foreign, unowned); `sent_by_human`
    and `is_autopilot_reply` are absent and get created fresh by upgrade()
    (owned, no data). Downgrade must drop only the two it owns and leave
    `whatsapp_instance` -- column AND its real data -- completely alone."""
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "whatsapp_instance varchar(128))"
            ))
            await conn.execute(text(
                "INSERT INTO messages (content, whatsapp_instance) "
                "VALUES ('conversa antiga da loja', 'loja')"
            ))
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.upgrade))

        async with engine.connect() as conn:
            owned = await _marker_rows(conn)
        assert owned == {"sent_by_human", "is_autopilot_reply", "ix_messages_whatsapp_instance"}

        async with engine.begin() as conn:
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.downgrade))  # must not raise

        async with engine.connect() as conn:
            cols = await _columns(conn)
            idx = await _indexes(conn)
            row = (await conn.execute(text(
                "SELECT content, whatsapp_instance FROM messages"
            ))).fetchone()
        assert "sent_by_human" not in cols
        assert "is_autopilot_reply" not in cols
        assert "whatsapp_instance" in cols  # preexisting, foreign -- left alone
        assert "ix_messages_whatsapp_instance" not in idx  # owned index still gets dropped
        assert row == ("conversa antiga da loja", "loja")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_removes_only_the_index_this_migration_created_leaving_a_preexisting_column_and_data_alone(isolated_db):
    """All three columns pre-exist with real data (foreign, unowned); only
    the index is absent and gets created by upgrade() (owned). Downgrade
    must drop only the index and leave every column -- and its data --
    completely untouched, proving index ownership is tracked independently
    of column ownership, in both directions."""
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "sent_by_human boolean not null default false, "
                "is_autopilot_reply boolean not null default false, "
                "whatsapp_instance varchar(128))"
            ))
            await conn.execute(text(
                "INSERT INTO messages (content, sent_by_human, whatsapp_instance) "
                "VALUES ('resposta real sem indice', true, 'dario')"
            ))
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.upgrade))

        async with engine.connect() as conn:
            owned = await _marker_rows(conn)
            idx = await _indexes(conn)
        assert owned == {"ix_messages_whatsapp_instance"}
        assert "ix_messages_whatsapp_instance" in idx

        async with engine.begin() as conn:
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.downgrade))  # must not raise

        async with engine.connect() as conn:
            cols = await _columns(conn)
            idx = await _indexes(conn)
            row = (await conn.execute(text(
                "SELECT content, sent_by_human, whatsapp_instance FROM messages"
            ))).fetchone()
        assert {"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} <= cols
        assert "ix_messages_whatsapp_instance" not in idx
        assert row == ("resposta real sem indice", True, "dario")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_refuses_rather_than_force_drop_a_column_coupled_to_an_unowned_index(isolated_db):
    """Defensive-only path: a pre-existing index without its column cannot
    be constructed in real SQL, so this exercises the guard by simulating
    marker corruption -- the index's ownership row is missing even though
    structurally both the column (owned) and the index exist. Dropping the
    owned column would force PostgreSQL to drop the index as a side
    effect; since the index's ownership can't be confirmed, downgrade must
    refuse entirely rather than silently take a possibly-foreign index
    down with it."""
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "contact_id integer, direction varchar(16))"
            ))
            await conn.run_sync(lambda c: _run_sync_migration(c, migration.upgrade))
            # Simulate marker corruption: forget that the index was ours,
            # while the column (and the index itself) structurally remain.
            await conn.execute(text(
                "DELETE FROM \"_mig_e610080003_created_objects\" WHERE object_name = 'ix_messages_whatsapp_instance'"
            ))

        with pytest.raises(Exception):
            async with engine.begin() as conn:
                await conn.run_sync(lambda c: _run_sync_migration(c, migration.downgrade))

        async with engine.connect() as conn:
            cols = await _columns(conn)
            idx = await _indexes(conn)
        assert "whatsapp_instance" in cols
        assert "ix_messages_whatsapp_instance" in idx
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_refuses_outright_when_the_old_global_marker_is_present(isolated_db):
    """The OLD, global-flag marker (from the previous version of this
    migration) proves only that upgrade() created SOMETHING, never which
    specific column(s)/index. It must never be reinterpreted under the new
    per-object scheme -- downgrade refuses on sight."""
    dbname = isolated_db
    engine = create_async_engine(_db_url(dbname))
    migration = _load_migration()
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE messages (id serial primary key, content text, "
                "sent_by_human boolean not null default false, "
                "is_autopilot_reply boolean not null default false, "
                "whatsapp_instance varchar(128))"
            ))
            await conn.execute(text(
                "CREATE TABLE \"_mig_e610080003_created_authorship_columns\" "
                "(created_at timestamp not null default now())"
            ))
            await conn.execute(text(
                "INSERT INTO \"_mig_e610080003_created_authorship_columns\" DEFAULT VALUES"
            ))

        with pytest.raises(Exception):
            async with engine.begin() as conn:
                await conn.run_sync(lambda c: _run_sync_migration(c, migration.downgrade))

        async with engine.connect() as conn:
            cols = await _columns(conn)
        assert {"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} <= cols
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
