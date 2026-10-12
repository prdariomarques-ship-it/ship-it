"""Migração `c8f3a1d27b40` (store_voice_sends, store_followups) pela CLI do alembic, como a CI faz, em SQLite descartável.

Cobre: sobe/desce vazia; as colunas migradas == as colunas dos modelos; o downgrade RECUSA remover histórico de envios.
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from database.base import Base
import models  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
REV = "c8f3a1d27b40"


def _alembic(db: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db}", "JWT_SECRET": "test-secret-key-with-enough-bytes-for-hs256", "ENVIRONMENT": "test"}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)


def _cols(db: Path, table: str) -> dict[str, tuple[str, int]]:
    con = sqlite3.connect(db)
    try:
        return {r[1]: (r[2].upper().split("(")[0], r[3]) for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


@pytest.fixture
def migrated(tmp_path):
    db = tmp_path / "m.db"
    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-800:]
    return db


def test_a_cabeca_e_a_migracao_nova(migrated):
    assert REV in _alembic(migrated, "current").stdout


@pytest.mark.parametrize("table", ["store_voice_sends", "store_followups"])
def test_colunas_migradas_batem_com_os_modelos(migrated, table):
    model = {c.name for c in Base.metadata.tables[table].columns}
    assert set(_cols(migrated, table)) == model
    notnull = {n for n, (_t, nn) in _cols(migrated, table).items() if nn}
    assert {"dedupe_key", "status", "contact_id", "created_at", "updated_at"} <= notnull


def test_downgrade_vazio_funciona_e_recria_ao_subir(migrated):
    down = _alembic(migrated, "downgrade", "-1")
    assert down.returncode == 0, down.stderr[-800:]
    con = sqlite3.connect(migrated)
    try:
        assert not list(con.execute("select name from sqlite_master where name in ('store_voice_sends','store_followups')"))
    finally:
        con.close()
    assert _alembic(migrated, "upgrade", "head").returncode == 0


@pytest.mark.parametrize("table", ["store_voice_sends", "store_followups"])
def test_downgrade_recusa_apagar_historico_de_envios(migrated, table):
    con = sqlite3.connect(migrated)
    con.execute("PRAGMA foreign_keys=OFF")
    if table == "store_voice_sends":
        con.execute("INSERT INTO store_voice_sends (dedupe_key,kind,contact_id,instance,status,script_text,attempts,history,created_at,updated_at) "
                    "VALUES ('k','reply',1,'MARQUESCOLOR','sent','x',0,'[]','2026-01-01','2026-01-01')")
    else:
        con.execute("INSERT INTO store_followups (dedupe_key,kind,contact_id,customer_id,instance,origin_type,origin_id,reason,due_at,status,attempts,max_attempts,snapshot,history,created_at,updated_at) "
                    "VALUES ('k','quote_resume',1,1,'MARQUESCOLOR','store_quote','o','r','2026-01-01','sent',1,1,'{}','[]','2026-01-01','2026-01-01')")
    con.commit()
    con.close()
    down = _alembic(migrated, "downgrade", "-1")
    assert down.returncode != 0 and "Recusado" in down.stderr
    assert REV in _alembic(migrated, "current").stdout          # permanece na revisão; nada foi apagado
    assert table in [r[0] for r in sqlite3.connect(migrated).execute("select name from sqlite_master where type='table'")]
