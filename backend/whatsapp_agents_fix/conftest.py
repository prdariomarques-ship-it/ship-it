"""Shared setup for this self-contained review/test package.

Why self-contained (not importing backend/'s real packages wholesale):
`backend/orchestrator/` and `backend/services/` are real Python packages
with real `__init__.py` files. Python cannot merge two same-named
packages living under different sys.path roots -- whichever comes first
wins ENTIRELY, pulling in every real sibling module (e.g. the real
`orchestrator.priority` drags in `orchestrator.intent` and
`providers.llm.*`, none of which this delivery's three source files
cover or this package stubs). Rather than risk an import chain that
*looks* wired to the real app but actually depends on untested,
unverified transitive modules, this package keeps its own copies of the
four pure-logic modules under review (`twin_risk_gate.py`,
`output_safety.py`, `incident_dedup.py` here; `conversation_control.py`
loaded by explicit path below) and verifies by hash, in
`test_review_copies_match_deployed_files.py`, that they are byte-identical
to what actually ships at `backend/orchestrator/` and
`backend/services/` (except for the one import-style difference
`incident_dedup.py` needs: package-qualified in the real deployed file,
flat here -- also checked explicitly, not just asserted in a comment).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
BACKEND_ROOT = HERE.parents[0]  # .../backend
APP_STUB = HERE / "app_stub"

if str(APP_STUB) not in sys.path:
    sys.path.insert(0, str(APP_STUB))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_real_module(qualified_name: str, real_path: Path):
    """Loads a module from its REAL, canonically-deployed path (under
    backend/) but registers it under `qualified_name` in sys.modules --
    so e.g. the real jobs/handlers.py's own `from services.output_safety
    import output_safe` resolves against another real-path-loaded module
    registered as `services.output_safety`, and `from jobs.registry
    import job_handler` resolves against app_stub's fake sibling. No
    static copy of handlers.py/router.py/conversation_control.py/
    output_safety.py is kept anywhere for this purpose -- these four are
    always loaded from their one real, deployed location."""
    spec = importlib.util.spec_from_file_location(qualified_name, real_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def real_control_db(tmp_path):
    """A real SQLite database, migrated with the real Alembic revisions
    this PR ships (backend/alembic/versions/e610080001_pause_control.py
    and e610080002_review_delivery.py), using the real
    backend/services/conversation_control.py module, loaded by its
    actual deployed path -- not a copy."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    control = _load(BACKEND_ROOT / "services" / "conversation_control.py", "real_conversation_control")
    migrations = [
        _load(BACKEND_ROOT / "alembic" / "versions" / "e610080001_pause_control.py", "mig_v1"),
        _load(BACKEND_ROOT / "alembic" / "versions" / "e610080002_review_delivery.py", "mig_v2"),
    ]
    db_path = tmp_path / "control.sqlite"
    sync_engine = create_engine(f"sqlite:///{db_path}")
    with sync_engine.begin() as conn:
        conn.execute(text("CREATE TABLE contacts (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO contacts VALUES (42)"))
        conn.execute(text("INSERT INTO contacts VALUES (43)"))
        conn.execute(text("INSERT INTO users VALUES (7)"))
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            for migration in migrations:
                migration.upgrade()
    sync_engine.dispose()

    async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    yield control, sessions
    await async_engine.dispose()
