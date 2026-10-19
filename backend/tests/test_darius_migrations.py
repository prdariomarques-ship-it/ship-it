"""Migrations `d91b5e7a3c20` (automation_suspensions) and `e7a42c9f1b35` (darius_whatsapp_tasks) through the alembic CLI,
as CI does, on a throwaway SQLite: up from the previous revision, the migrated columns equal the ORM models, the UNIQUE
arbiters exist, and the downgrades return to the previous revision."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import models  # noqa: F401 -- registers every table on Base.metadata
from database.base import Base

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = "c8f3a1d27b40"
SUSPENSION = "d91b5e7a3c20"
DARIUS = "e7a42c9f1b35"


def _alembic(db: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db}",
        "JWT_SECRET": "test-secret-key-with-enough-bytes-for-hs256", "ENVIRONMENT": "test",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180
    )


def _tables(db: Path) -> set[str]:
    con = sqlite3.connect(db)
    try:
        return {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    finally:
        con.close()


def _columns(db: Path, table: str) -> set[str]:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


def _unique_columns(db: Path, table: str) -> set[tuple[str, ...]]:
    con = sqlite3.connect(db)
    try:
        found: set[tuple[str, ...]] = set()
        for _seq, name, unique, *_ in con.execute(f"PRAGMA index_list({table})"):
            if unique:
                found.add(tuple(r[2] for r in con.execute(f"PRAGMA index_info({name})")))
        return found
    finally:
        con.close()


@pytest.fixture
def at_previous(tmp_path):
    db = tmp_path / "m.db"
    assert _alembic(db, "upgrade", PREVIOUS).returncode == 0
    return db


@pytest.mark.parametrize(("revision", "table"), [(SUSPENSION, "automation_suspensions"), (DARIUS, "darius_whatsapp_tasks")])
def test_the_migration_creates_exactly_the_model_columns(at_previous, revision, table):
    assert table not in _tables(at_previous)
    up = _alembic(at_previous, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-800:]
    assert revision in _alembic(at_previous, "history").stdout
    assert _columns(at_previous, table) == {c.name for c in Base.metadata.tables[table].columns}


def test_the_unique_arbiters_exist(at_previous):
    assert _alembic(at_previous, "upgrade", "head").returncode == 0
    assert ("dedupe_key",) in _unique_columns(at_previous, "darius_whatsapp_tasks")
    # the suspension scope is the primary key (the atomic arbiter): SQLite reports it as an auto index
    model_pk = [c.name for c in Base.metadata.tables["automation_suspensions"].primary_key.columns]
    assert model_pk and tuple(model_pk) in _unique_columns(at_previous, "automation_suspensions")


def test_downgrades_walk_back_one_revision_at_a_time(at_previous):
    assert _alembic(at_previous, "upgrade", "head").returncode == 0
    down = _alembic(at_previous, "downgrade", SUSPENSION)
    assert down.returncode == 0, down.stderr[-800:]
    assert "darius_whatsapp_tasks" not in _tables(at_previous) and "automation_suspensions" in _tables(at_previous)
    down = _alembic(at_previous, "downgrade", PREVIOUS)
    assert down.returncode == 0, down.stderr[-800:]
    assert "automation_suspensions" not in _tables(at_previous)
    assert PREVIOUS in _alembic(at_previous, "current").stdout
    assert _alembic(at_previous, "upgrade", "head").returncode == 0           # and the cycle closes again
