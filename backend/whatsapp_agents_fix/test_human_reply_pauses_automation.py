"""Real execution of the REAL `webhooks/router.py`'s `_capture_human_reply`
-- loaded by its actual deployed path, against REAL Contact/User/Message
ORM models and the REAL `services/conversation_control.py`, migrated with
the REAL Alembic revisions this review ships.

Review fix (D): `_capture_human_reply` persisted the owner's reply and
cleared `awaiting_reply_since`, but never called `conversation_control.pause`
-- test_pause_fencing.py's 5 passing tests prove the pause/claim_send fence
works once triggered; none of them prove a REAL incoming human-reply event
actually triggers it. This file is what does: it calls the real function,
then checks the real `conversation_controls` table, not a mock of
conversation_control.

Honest limit: exercises the `personal_empty_audio` branch (an owner audio
reply with no transcribed text yet on the personal instance), because the
text-reply branch calls `MessageRepository.find_unacknowledged_outbound` --
a method that does not exist anywhere in the real repository (a separate,
newly confirmed gap, documented in SESSION_TRACKING.md, not fixed here
since its intended matching semantics aren't evidenced anywhere and
guessing them risks getting the echo-detection logic wrong). The pause-wiring
code added by this fix runs identically on both branches -- same call,
same place in the function, same commit -- so this still proves the real
fix, just via the one branch that is actually callable today.

Isolation note: see test_persist_outbound_message_real_execution.py's
module docstring -- the same `sys.modules` leak risk applies here (even
more so: this file loads models.contact/user/message/job and
repositories.*, all real), so loading happens inside a module-scoped
fixture with teardown, not at import time.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from conftest import load_real_module

HERE = Path(__file__).parent
BACKEND_ROOT = HERE.parents[0]
APP_STUB = str(HERE / "app_stub")
if APP_STUB not in sys.path:
    sys.path.insert(0, APP_STUB)

_REAL_MODULE_KEYS = (
    "database.base", "models.contact", "models.user", "models.message", "models.job",
    "repositories.base", "repositories.user", "repositories.message",
    "services.conversation_control", "webhooks.router",
)


def _migrate_control_tables_sync(sync_conn):
    import importlib.util

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migrations = [
        load("mig_v1_human_reply", BACKEND_ROOT / "alembic" / "versions" / "e610080001_pause_control.py"),
        load("mig_v2_human_reply", BACKEND_ROOT / "alembic" / "versions" / "e610080002_review_delivery.py"),
    ]
    ctx = MigrationContext.configure(sync_conn)
    with Operations.context(ctx):
        for migration in migrations:
            migration.upgrade()


@pytest.fixture(scope="module", autouse=True)
def _real_modules():
    saved = {key: sys.modules.get(key) for key in _REAL_MODULE_KEYS}
    try:
        # Dependency order: database.base -> contact/user/message/job (all
        # only depend on database.base) -> repositories (depend on the
        # models) -> conversation_control (standalone, raw SQL) -> router
        # (depends on everything above, plus app_stub for the rest).
        load_real_module("database.base", BACKEND_ROOT / "database" / "base.py")
        load_real_module("models.contact", BACKEND_ROOT / "models" / "contact.py")
        load_real_module("models.user", BACKEND_ROOT / "models" / "user.py")
        load_real_module("models.message", BACKEND_ROOT / "models" / "message.py")
        load_real_module("models.job", BACKEND_ROOT / "models" / "job.py")
        load_real_module("repositories.base", BACKEND_ROOT / "repositories" / "base.py")
        load_real_module("repositories.user", BACKEND_ROOT / "repositories" / "user.py")
        load_real_module("repositories.message", BACKEND_ROOT / "repositories" / "message.py")
        load_real_module("services.conversation_control", BACKEND_ROOT / "services" / "conversation_control.py")
        load_real_module("webhooks.router", BACKEND_ROOT / "webhooks" / "router.py")
        yield
    finally:
        for key, mod in saved.items():
            if mod is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = mod


@pytest.fixture
def router(_real_modules):
    return sys.modules["webhooks.router"]


@pytest.fixture
def conversation_control(_real_modules):
    return sys.modules["services.conversation_control"]


@pytest_asyncio.fixture
async def real_db(_real_modules):
    Base = sys.modules["database.base"].Base
    Contact = sys.modules["models.contact"].Contact
    User = sys.modules["models.user"].User
    UserRole = sys.modules["models.user"].UserRole

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        # contacts/users/messages/jobs from the real ORM models loaded
        # above; conversation_controls/_audit/_send_intents/_alert_intents
        # from the real Alembic migrations (not ORM-backed -- raw SQL).
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_control_tables_sync)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as db:
        contact = Contact(name="Flávio", phone="+5511999990000")
        owner = User(email="owner@example.com", full_name="Dário", hashed_password="x", role=UserRole.ADMIN)
        db.add_all([contact, owner])
        await db.commit()
        await db.refresh(contact)
        await db.refresh(owner)
    yield sessions, Contact, contact.id, owner.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_real_owner_reply_actually_pauses_automation_for_that_contact_and_instance(router, real_db):
    sessions, Contact, contact_id, owner_id = real_db
    from utils.config import get_settings
    settings = get_settings()
    original_personal_instance = settings.evolution_personal_instance
    settings.evolution_personal_instance = "dario"
    try:
        inbound = SimpleNamespace(
            phone="+5511988880000", text="", external_id="evt-1", timestamp=datetime.now(timezone.utc),
            instance="dario", media_key="some-media-key",
        )
        provider = SimpleNamespace(name="evolution")
        async with sessions() as db:
            contact = (await db.execute(select(Contact).where(Contact.id == contact_id))).scalar_one()
            ack = await router._capture_human_reply(db, provider, contact, inbound, "audio")
        assert ack.status == "human_reply_captured"

        async with sessions() as db:
            row = (await db.execute(text(
                "SELECT paused, revision FROM conversation_controls WHERE contact_id=:cid AND instance=:inst"
            ), {"cid": contact_id, "inst": "dario"})).mappings().first()
        assert row is not None, "o evento real nao criou nenhuma linha de controle -- pause() nunca foi chamado"
        assert bool(row["paused"]) is True
        assert row["revision"] == 1

        async with sessions() as db:
            audit = (await db.execute(text(
                "SELECT action, reason, actor_id FROM conversation_control_audit "
                "WHERE contact_id=:cid AND instance=:inst ORDER BY id DESC LIMIT 1"
            ), {"cid": contact_id, "inst": "dario"})).mappings().first()
        assert audit is not None
        assert audit["action"] == "pause"
        assert audit["reason"] == "owner_replied"
        assert audit["actor_id"] == owner_id
    finally:
        settings.evolution_personal_instance = original_personal_instance


@pytest.mark.asyncio
async def test_pause_from_the_real_event_actually_blocks_a_stale_queued_send(router, conversation_control, real_db):
    """End-to-end tie-in: the pause this real event triggers must be the
    SAME fence test_pause_fencing.py already proves works -- not a
    parallel, disconnected mechanism. A send captured BEFORE this reply,
    with the pre-reply revision, must still be blocked by claim_send after."""
    sessions, Contact, contact_id, owner_id = real_db
    from utils.config import get_settings
    settings = get_settings()
    original_personal_instance = settings.evolution_personal_instance
    settings.evolution_personal_instance = "dario"
    try:
        async with sessions() as db:
            stale_revision = (await conversation_control.snapshot(db, contact_id, "dario"))["revision"]

        inbound = SimpleNamespace(
            phone="+5511988880000", text="", external_id="evt-2", timestamp=datetime.now(timezone.utc),
            instance="dario", media_key="some-media-key",
        )
        provider = SimpleNamespace(name="evolution")
        async with sessions() as db:
            contact = (await db.execute(select(Contact).where(Contact.id == contact_id))).scalar_one()
            await router._capture_human_reply(db, provider, contact, inbound, "audio")

        async with sessions() as db:
            outcome = await conversation_control.claim_send(
                db, contact_id, "dario", stale_revision, "twin-send:stale-test",
            )
            await db.commit()
        assert outcome == "suppressed"
    finally:
        settings.evolution_personal_instance = original_personal_instance


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
