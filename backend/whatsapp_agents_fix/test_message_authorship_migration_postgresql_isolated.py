"""Real PostgreSQL 16 (local to this sandbox), proving e610080003's
upgrade/downgrade behavior against the four scenarios the review asked
for -- not just read as source, actually run against a real database:

  1. A database WITHOUT the three columns: upgrade() actually adds them.
  2. A database WITH the columns and real historical data (simulating
     production, where they pre-existed before this migration's upgrade()
     ever ran there): upgrade() is a true no-op -- no duplicate-column
     error, no data touched.
  3. Downgrade on a database carrying real data in those columns: refuses
     (raises), and the columns/data are verified still present afterward
     -- not "probably didn't drop them", actually queried.
  4. Downgrade on a database where the columns exist but carry no data
     (the genuinely safe case -- a fresh DB that just ran upgrade()):
     succeeds and actually removes them.

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


@pytest.mark.asyncio
async def test_upgrade_adds_the_three_columns_when_absent(isolated_db):
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
            cols = {row[0] for row in (await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='messages'"
            ))).fetchall()}
        assert {"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} <= cols
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_upgrade_is_a_true_noop_when_columns_and_data_already_exist(isolated_db):
    """The real production scenario: columns with real historical data
    already there BEFORE this migration's upgrade() ever runs."""
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
        assert len(rows) == 2
        assert rows[0] == ("resposta real do dono", True, False, "dario")
        assert rows[1] == ("resposta automatica real", False, True, "azusa-church")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_refuses_and_preserves_real_data(isolated_db):
    """The scenario the review flagged: a database that has processed real
    messages must never have this data silently dropped by a 003->002
    downgrade. Must raise BEFORE removing anything, not after."""
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
            cols = {row[0] for row in (await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='messages'"
            ))).fetchall()}
            row = (await conn.execute(text(
                "SELECT content, sent_by_human, whatsapp_instance FROM messages"
            ))).fetchone()
        assert {"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} <= cols
        assert row == ("historico real do proprietario", True, "dario")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_succeeds_when_columns_exist_but_carry_no_data(isolated_db):
    """The genuinely safe case: a fresh database that just ran upgrade()
    and never processed a real message through these columns. Downgrade
    here is a real, clean revert -- proving the block above is about real
    data, not a blanket refusal to ever downgrade."""
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
            cols = {row[0] for row in (await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='messages'"
            ))).fetchall()}
        assert not ({"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} & cols)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
