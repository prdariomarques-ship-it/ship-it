"""Real PostgreSQL 16 (local to this sandbox, started earlier this
session -- `service postgresql start`, confirmed via `psql`), not SQLite.

Every test here creates its OWN disposable database
(`whatsapp_dedup_pg_<uuid>`), migrates it with the real Alembic revisions
this package ships, runs incident_dedup.decide_owner_alert /
conversation_control.alert_claim against it, and drops the database in
teardown. Nothing here is shared state with any other test file, and
nothing here touches the application/dev databases this sandbox also
has (chroma_pause_test_main, whatsapp_test).

This directly answers the review's four asks for dedup_key specifically
(not conversation_control's own generic send/pause mechanism, which the
V2 package's own opt-in Postgres test already covers -- see
DELIVERY_NOTES.md section 2.1):

  1. two workers -- two separate asyncpg connections (via two separate
     async engines, not two sessions sharing one engine/pool) racing the
     SAME incident+evidence concurrently;
  2. repetition -- the same evidence claimed again after the first
     success is suppressed;
  3. reinício (restart) -- the engine/connection pool used by "worker 1"
     is fully disposed and a BRAND NEW engine is created against the
     same database, simulating a fresh process with no shared Python
     state (no cached objects, no connection reuse) -- and the dedup
     state is still correctly there.

Opt-in only, same pattern as the V2 package's own
tests/test_postgres_opt_in.py: no connection string is hardcoded here.
Set WHATSAPP_DEDUP_PG_ADMIN_URL to a disposable-fixture admin connection
(e.g. "postgresql+asyncpg://<user>:<password>@127.0.0.1/postgres" for a
role that can CREATE/DROP DATABASE) before running this file; without it,
every test here is skipped, not run against any guessed or default
credential.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from conftest import load_real_module
from incident_dedup import decide_owner_alert
from twin_risk_gate import MessageAuthor, RiskEvidence

# Real deployed module, loaded by its actual path -- not a copy. See
# conftest.py's load_real_module docstring for why.
conversation_control = load_real_module(
    "services.conversation_control",
    Path(__file__).parents[1] / "services" / "conversation_control.py",
)

ADMIN_URL = os.environ.get("WHATSAPP_DEDUP_PG_ADMIN_URL")
NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)

pytestmark = pytest.mark.skipif(
    not ADMIN_URL,
    reason="WHATSAPP_DEDUP_PG_ADMIN_URL not set -- no PostgreSQL admin connection configured, skipping real-Postgres tests",
)


def _db_url(dbname: str) -> str:
    # plain str(url) masks the password as "***" -- must render explicitly.
    return make_url(ADMIN_URL).set(database=dbname).render_as_string(hide_password=False)


def _evidence(snippet: str = "culpa") -> RiskEvidence:
    return RiskEvidence(
        category="crise", snippet=snippet, source_message_id=1,
        source_author=MessageAuthor.CLIENT, source_created_at=NOW, in_current_message=False,
    )


async def _create_and_migrate(dbname: str) -> None:
    from alembic.migration import MigrationContext

    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    await admin.dispose()

    engine = create_async_engine(_db_url(dbname))
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE contacts (id INTEGER PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        await conn.execute(text("INSERT INTO contacts VALUES (42), (43)"))
        await conn.execute(text("INSERT INTO users VALUES (7)"))

        def upgrade(sync_conn):
            import importlib.util
            from pathlib import Path

            def load(name, path):
                spec = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module

            backend_root = Path(__file__).parent.parents[0]  # .../backend
            migrations = [
                load("pg_mig_v1", backend_root / "alembic" / "versions" / "e610080001_pause_control.py"),
                load("pg_mig_v2", backend_root / "alembic" / "versions" / "e610080002_review_delivery.py"),
            ]
            ctx = MigrationContext.configure(sync_conn)
            from alembic.operations import Operations as Ops
            with Ops.context(ctx):
                for migration in migrations:
                    migration.upgrade()

        await conn.run_sync(upgrade)
    await engine.dispose()


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
async def isolated_pg_db():
    dbname = f"whatsapp_dedup_pg_{uuid.uuid4().hex[:12]}"
    try:
        await _create_and_migrate(dbname)
    except Exception:
        # A failure during CREATE DATABASE/migration must not orphan the
        # database it already created -- drop it before re-raising, same
        # guarantee the happy path gets from the try/finally below.
        await _drop_database(dbname)
        raise
    try:
        yield dbname
    finally:
        await _drop_database(dbname)


def _sessions_for(dbname: str):
    """A fresh engine + sessionmaker -- each call simulates a distinct
    process/worker with its own connection pool, no shared state."""
    engine = create_async_engine(_db_url(dbname))
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_two_independent_workers_concurrently_claim_the_same_evidence_only_one_wins(isolated_pg_db):

    dbname = isolated_pg_db
    evidence = _evidence(snippet="culpa")

    # Two SEPARATE engines/connection pools -- not two sessions sharing
    # one pool -- genuinely simulating two separate worker processes.
    engine_a, sessions_a = _sessions_for(dbname)
    engine_b, sessions_b = _sessions_for(dbname)

    async def worker(sessions):
        async with sessions() as db:
            decision = await decide_owner_alert(
                conversation_control, db, contact_id=42, instance="dario",
                evidence=evidence, window_seconds=3600, now=NOW,
            )
            await db.commit()
            return decision.should_alert

    try:
        results = await asyncio.gather(worker(sessions_a), worker(sessions_b))
    finally:
        await engine_a.dispose()
        await engine_b.dispose()

    assert sorted(results) == [False, True]


@pytest.mark.asyncio
async def test_repetition_after_first_claim_is_suppressed_on_real_postgres(isolated_pg_db):

    dbname = isolated_pg_db
    evidence = _evidence(snippet="culpa")
    engine, sessions = _sessions_for(dbname)
    try:
        async with sessions() as db:
            first = await decide_owner_alert(conversation_control, db, contact_id=42, instance="dario", evidence=evidence, window_seconds=3600, now=NOW)
            await db.commit()
        async with sessions() as db:
            second = await decide_owner_alert(conversation_control, db, contact_id=42, instance="dario", evidence=evidence, window_seconds=3600, now=NOW)
            await db.commit()
        async with sessions() as db:
            third = await decide_owner_alert(conversation_control, db, contact_id=42, instance="dario", evidence=evidence, window_seconds=3600, now=NOW)
            await db.commit()
    finally:
        await engine.dispose()

    assert (first.should_alert, second.should_alert, third.should_alert) == (True, False, False)


@pytest.mark.asyncio
async def test_claim_survives_a_simulated_restart_fresh_engine_no_shared_state(isolated_pg_db):
    """'Worker 1' claims the evidence, then its ENTIRE engine/connection
    pool is disposed (no Python object, cache, or connection survives).
    A brand new engine -- standing in for a freshly-started process -- is
    created against the same database and must see the claim as already
    made, proving the state lives in PostgreSQL itself, not in-process
    memory."""

    dbname = isolated_pg_db
    evidence = _evidence(snippet="culpa")

    engine_1, sessions_1 = _sessions_for(dbname)
    async with sessions_1() as db:
        first = await decide_owner_alert(conversation_control, db, contact_id=42, instance="dario", evidence=evidence, window_seconds=3600, now=NOW)
        await db.commit()
    await engine_1.dispose()  # "process 1" is gone -- no shared state survives this line

    # "Restart": a completely fresh engine/pool, new TCP connections, new
    # asyncpg protocol state -- nothing reused from engine_1.
    engine_2, sessions_2 = _sessions_for(dbname)
    try:
        async with sessions_2() as db:
            after_restart = await decide_owner_alert(conversation_control, db, contact_id=42, instance="dario", evidence=evidence, window_seconds=3600, now=NOW)
            await db.commit()
    finally:
        await engine_2.dispose()

    assert first.should_alert is True
    assert after_restart.should_alert is False  # the "new process" sees the real, persisted claim


@pytest.mark.asyncio
async def test_genuinely_new_evidence_still_escalates_after_restart_on_real_postgres(isolated_pg_db):

    dbname = isolated_pg_db
    mild = _evidence(snippet="culpa")
    severe = _evidence(snippet="suicidio")

    engine_1, sessions_1 = _sessions_for(dbname)
    async with sessions_1() as db:
        first = await decide_owner_alert(conversation_control, db, contact_id=42, instance="dario", evidence=mild, window_seconds=3600, now=NOW)
        await db.commit()
    await engine_1.dispose()

    engine_2, sessions_2 = _sessions_for(dbname)
    try:
        async with sessions_2() as db:
            second = await decide_owner_alert(conversation_control, db, contact_id=42, instance="dario", evidence=severe, window_seconds=3600, now=NOW)
            await db.commit()
    finally:
        await engine_2.dispose()

    assert first.should_alert is True
    assert second.should_alert is True  # different, more severe evidence -- still escalates post-restart


@pytest.mark.asyncio
async def test_ten_concurrent_workers_same_evidence_exactly_one_wins_on_real_postgres(isolated_pg_db):
    """Scaled-up version of the two-worker test -- 10 separate engines
    (10 separate connection pools), not 10 tasks sharing one pool."""

    dbname = isolated_pg_db
    evidence = _evidence(snippet="culpa")
    engines_and_sessions = [_sessions_for(dbname) for _ in range(10)]

    async def worker(sessions):
        async with sessions() as db:
            decision = await decide_owner_alert(conversation_control, db, contact_id=42, instance="dario", evidence=evidence, window_seconds=3600, now=NOW)
            await db.commit()
            return decision.should_alert

    try:
        results = await asyncio.gather(*[worker(sessions) for _, sessions in engines_and_sessions])
    finally:
        await asyncio.gather(*[engine.dispose() for engine, _ in engines_and_sessions])

    assert results.count(True) == 1
    assert results.count(False) == 9


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
