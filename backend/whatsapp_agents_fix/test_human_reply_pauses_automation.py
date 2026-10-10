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

Review fix (round 4, finding #2): the module above used to stop at the
`personal_empty_audio` branch because `MessageRepository.find_unacknowledged_outbound`
did not exist anywhere in the real repository, and the text-reply branch
calls it unconditionally. It is now implemented (repositories/message.py)
and exercised below by the TEXT-reply branch's two distinct outcomes:

  - a genuine human reply (no matching unacknowledged outbound row for
    this contact/instance/content) -- creates a new Message row with
    `sent_by_human=True` and pauses automation, same as the audio branch.
  - the bot's own delivery echo (an unacknowledged, `is_autopilot_reply`
    row with the SAME content already sitting in the table, as if this
    system had just sent it) -- attaches the webhook's `external_id` to
    THAT existing row, creates no new Message row, and must NOT pause
    automation (it is not a human event at all). The review's explicit
    warning -- "não trate todo fromMe como humano" -- is exactly this
    distinction.

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


@pytest.mark.asyncio
async def test_a_genuine_text_reply_with_no_matching_outbound_row_is_captured_as_human(
    router, real_db,
):
    """No row this system sent matches the echoed text -- this must be
    treated as a real human reply: a new Message row with sent_by_human
    is created, and automation is paused, exactly like the audio branch."""
    sessions, Contact, contact_id, owner_id = real_db
    from utils.config import get_settings
    settings = get_settings()
    original_personal_instance = settings.evolution_personal_instance
    settings.evolution_personal_instance = "dario"
    try:
        inbound = SimpleNamespace(
            phone="+5511988880000", text="Pode vir que eu mesmo respondo daqui",
            external_id="evt-text-1", timestamp=datetime.now(timezone.utc),
            instance="dario", media_key=None,
        )
        provider = SimpleNamespace(name="evolution")
        async with sessions() as db:
            contact = (await db.execute(select(Contact).where(Contact.id == contact_id))).scalar_one()
            ack = await router._capture_human_reply(db, provider, contact, inbound, "text")
        assert ack.status == "human_reply_captured"

        Message = sys.modules["models.message"].Message
        async with sessions() as db:
            message = (await db.execute(select(Message).where(Message.id == ack.message_id))).scalar_one()
        assert message.sent_by_human is True
        assert message.is_autopilot_reply is False
        assert message.content == inbound.text
        assert message.external_id == "evt-text-1"

        async with sessions() as db:
            row = (await db.execute(text(
                "SELECT paused FROM conversation_controls WHERE contact_id=:cid AND instance=:inst"
            ), {"cid": contact_id, "inst": "dario"})).mappings().first()
        assert row is not None and bool(row["paused"]) is True
    finally:
        settings.evolution_personal_instance = original_personal_instance


@pytest.mark.asyncio
async def test_the_bots_own_echo_is_not_captured_as_a_human_reply(router, real_db):
    """Review warning, verbatim: 'não trate todo fromMe como humano'. An
    unacknowledged, is_autopilot_reply row with the SAME content already
    in the table (as if jobs/handlers.py's send_whatsapp_text had just
    sent it) is this system's own delivery echo bouncing back through the
    webhook -- not a human typing. Must attach the receipt id to THAT
    row, create no new Message, and must NOT pause automation."""
    sessions, Contact, contact_id, owner_id = real_db
    from utils.config import get_settings
    settings = get_settings()
    original_personal_instance = settings.evolution_personal_instance
    settings.evolution_personal_instance = "dario"
    try:
        Message = sys.modules["models.message"].Message
        MessageDirection = sys.modules["models.message"].MessageDirection
        async with sessions() as db:
            sent = Message(
                contact_id=contact_id, direction=MessageDirection.OUTBOUND,
                content="Claro, posso te ajudar com isso!",
                is_autopilot_reply=True, whatsapp_instance="dario",
            )
            db.add(sent)
            await db.commit()
            await db.refresh(sent)
            sent_id = sent.id

        async with sessions() as db:
            count_before = (await db.execute(text("SELECT COUNT(*) FROM messages"))).scalar_one()

        inbound = SimpleNamespace(
            phone="+5511988880000", text="Claro, posso te ajudar com isso!",
            external_id="evt-echo-1", timestamp=datetime.now(timezone.utc),
            instance="dario", media_key=None,
        )
        provider = SimpleNamespace(name="evolution")
        async with sessions() as db:
            contact = (await db.execute(select(Contact).where(Contact.id == contact_id))).scalar_one()
            ack = await router._capture_human_reply(db, provider, contact, inbound, "text")
        assert ack.status == "own_echo"
        assert ack.message_id == sent_id

        async with sessions() as db:
            count_after = (await db.execute(text("SELECT COUNT(*) FROM messages"))).scalar_one()
            updated = (await db.execute(select(Message).where(Message.id == sent_id))).scalar_one()
        assert count_after == count_before, "criou uma linha nova em vez de reutilizar o eco do proprio envio"
        assert updated.external_id == "evt-echo-1"
        assert updated.sent_by_human is False

        async with sessions() as db:
            row = (await db.execute(text(
                "SELECT paused FROM conversation_controls WHERE contact_id=:cid AND instance=:inst"
            ), {"cid": contact_id, "inst": "dario"})).mappings().first()
        assert row is None, "o eco do proprio bot pausou a automacao -- isso nao e um evento humano"
    finally:
        settings.evolution_personal_instance = original_personal_instance


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
