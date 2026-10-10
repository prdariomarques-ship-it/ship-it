"""Real PostgreSQL 16 (local to this sandbox), proving this repository's
OWN alembic migration chain -- from blank to head and back to base -- is
mechanically traversable end to end, via `alembic`'s real CLI commands
(the exact ones CI's "Migrations apply and roll back" step runs), not
just read as source.

Review finding (round 6, "não inventar a migração histórica ausente"):
an earlier fix made `alembic upgrade head` / `downgrade base` work
against a blank SQLite database by adding a placeholder revision for
`9e2f1c6d7a80` (production's real alembic head id, confirmed via VPS
relay in an earlier round) with an INVENTED merge parentage onto this
repository's own two pre-existing chain heads. That merge was never
verified against production and is now explicitly marked BLOCKED (see
alembic/versions/9e2f1c6d7a80_production_baseline_marker.py's docstring).

This test deliberately does NOT claim to validate equivalence with
production -- it cannot, since the real content of that gap is
unavailable in this repository or this session (no VPS shell access).
What it DOES prove, which a SQLite-only check does not: this repository's
own graph, exactly as committed, is traversable through a SECOND database
engine too (PostgreSQL, matching production's real engine) -- not merely
"some SQL happened to work on SQLite's more permissive DDL". A cross-
engine cycle failure would be a real, repository-level bug; success is
necessary but explicitly NOT sufficient evidence of production parity.

Opt-in only, same pattern as test_dedup_key_postgresql_isolated.py: set
WHATSAPP_DEDUP_PG_ADMIN_URL before running; without it, this test is
skipped, not run against any guessed or default credential.
"""

from __future__ import annotations

import os
import subprocess
import sys
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
    dbname = f"whatsapp_full_chain_cycle_{uuid.uuid4().hex[:12]}"
    try:
        await _create_database(dbname)
    except Exception:
        await _drop_database(dbname)
        raise
    try:
        yield dbname
    finally:
        await _drop_database(dbname)


def _run_alembic(*args: str, dbname: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DATABASE_URL"] = _db_url(dbname).replace("postgresql+asyncpg", "postgresql+asyncpg")
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.asyncio
async def test_full_chain_upgrade_head_then_downgrade_base_round_trips_cleanly_on_postgresql(isolated_db):
    """The exact two commands CI's "Migrations apply and roll back" step
    runs, via the real `alembic` CLI (not a hand-rolled MigrationContext),
    against a brand-new, blank, isolated PostgreSQL database."""
    dbname = isolated_db

    upgrade = _run_alembic("upgrade", "head", dbname=dbname)
    assert upgrade.returncode == 0, (
        f"alembic upgrade head failed against isolated PostgreSQL:\n"
        f"stdout:\n{upgrade.stdout}\nstderr:\n{upgrade.stderr}"
    )

    engine = create_async_engine(_db_url(dbname))
    try:
        async with engine.connect() as conn:
            cols = {row[0] for row in (await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='messages'"
            ))).fetchall()}
        assert {"sent_by_human", "is_autopilot_reply", "whatsapp_instance"} <= cols
    finally:
        await engine.dispose()

    downgrade = _run_alembic("downgrade", "base", dbname=dbname)
    assert downgrade.returncode == 0, (
        f"alembic downgrade base failed against isolated PostgreSQL:\n"
        f"stdout:\n{downgrade.stdout}\nstderr:\n{downgrade.stderr}"
    )

    engine = create_async_engine(_db_url(dbname))
    try:
        async with engine.connect() as conn:
            tables = {row[0] for row in (await conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            ))).fetchall()}
        # A full downgrade to base must leave no application tables behind
        # (alembic's own bookkeeping table is the only thing that may remain).
        assert tables <= {"alembic_version"}
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
