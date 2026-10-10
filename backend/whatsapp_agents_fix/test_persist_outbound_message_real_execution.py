"""Real execution of the REAL `services/messaging.py` persist_outbound_message
-- loaded by its actual deployed path, not a copy, not AST-inspected.

Review fix (C), second half: jobs/handlers.py's send_whatsapp_text calls
`persist_outbound_message(db, to, content, is_autopilot_reply=..., instance=...)`,
but the real function's signature, before this fix, was
`(db, phone, content, media_type=...)` -- no `is_autopilot_reply`, no
`instance`. Every real call would have raised TypeError. This proves the
fixed signature actually accepts both and actually persists them onto the
Message row, against a REAL SQLite table built from the REAL Message model
(backend/models/message.py) -- not the harness's fake placeholder class,
which has no columns at all and could never have caught this.

Isolation note: `load_real_module` registers modules under their real
dotted name in the GLOBAL `sys.modules`, which every other test file in
this session also sees. Other files (test_send_whatsapp_text_real_execution.py)
deliberately rely on `services.messaging`/`models.message` resolving to
app_stub's FAKE versions instead. To avoid leaking this file's real
modules into those (collection happens for every file before any test
runs, but a module-scoped fixture's setup/teardown is scoped to when
THIS file's tests actually execute), the loading happens inside a
fixture with proper teardown, not at import time.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from conftest import load_real_module

HERE = Path(__file__).parent
BACKEND_ROOT = HERE.parents[0]
APP_STUB = str(HERE / "app_stub")
if APP_STUB not in sys.path:
    sys.path.insert(0, APP_STUB)

_REAL_MODULE_KEYS = ("database.base", "models.contact", "models.message", "services.messaging")


@pytest.fixture(scope="module", autouse=True)
def _load_real_modules_scoped_to_this_file():
    saved = {key: sys.modules.get(key) for key in _REAL_MODULE_KEYS}
    try:
        # Dependency order: database.base first (no further unresolved
        # real deps); models.contact next (Message.contact =
        # relationship("Contact", ...) resolves by class name in the
        # shared mapper registry -- SQLAlchemy can't configure the
        # Message mapper without it); then models.message; then the
        # module under test.
        load_real_module("database.base", BACKEND_ROOT / "database" / "base.py")
        load_real_module("models.contact", BACKEND_ROOT / "models" / "contact.py")
        load_real_module("models.message", BACKEND_ROOT / "models" / "message.py")
        load_real_module("services.messaging", BACKEND_ROOT / "services" / "messaging.py")
        yield
    finally:
        for key, mod in saved.items():
            if mod is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = mod


@pytest.fixture
def messaging(_load_real_modules_scoped_to_this_file):
    return sys.modules["services.messaging"]


@pytest.fixture
def real_base(_load_real_modules_scoped_to_this_file):
    return sys.modules["database.base"].Base


@pytest_asyncio.fixture
async def messages_table_db(real_base):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        # Only models.message/models.contact have been imported against
        # this Base, so create_all builds exactly "contacts" + "messages"
        # -- the real schema (including sent_by_human/is_autopilot_reply/
        # whatsapp_instance, confirmed via \d messages against the real
        # production database, see SESSION_TRACKING.md).
        await conn.run_sync(real_base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    yield sessions
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_outbound_message_accepts_is_autopilot_reply_and_instance(messaging, messages_table_db):
    async with messages_table_db() as db:
        message = await messaging.persist_outbound_message(
            db, "+5511999990000", "Oi! Temos o thinner 5L disponível, R$ 45,00.",
            is_autopilot_reply=True, instance="dario",
        )
        assert message.is_autopilot_reply is True
        assert message.whatsapp_instance == "dario"


@pytest.mark.asyncio
async def test_persisted_row_really_has_the_values_not_just_the_in_memory_object(messaging, messages_table_db):
    async with messages_table_db() as db:
        await messaging.persist_outbound_message(
            db, "+5511999990000", "Mensagem de teste",
            is_autopilot_reply=True, instance="azusa-church",
        )

    async with messages_table_db() as db:
        row = (await db.execute(text(
            "SELECT is_autopilot_reply, whatsapp_instance, sent_by_human FROM messages "
            "WHERE content = 'Mensagem de teste'"
        ))).mappings().first()

    assert row is not None
    assert bool(row["is_autopilot_reply"]) is True
    assert row["whatsapp_instance"] == "azusa-church"
    assert bool(row["sent_by_human"]) is False  # default, untouched by this call


@pytest.mark.asyncio
async def test_default_call_still_behaves_like_the_old_dashboard_triggered_path(messaging, messages_table_db):
    """Backward compatibility: api/whatsapp.py's call site (the other
    caller documented in this module's own docstring) never passes
    is_autopilot_reply/instance at all -- both must still default safely."""
    async with messages_table_db() as db:
        message = await messaging.persist_outbound_message(
            db, "+5511999990000", "Mensagem manual do painel",
        )
        assert message.is_autopilot_reply is False
        assert message.whatsapp_instance is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
