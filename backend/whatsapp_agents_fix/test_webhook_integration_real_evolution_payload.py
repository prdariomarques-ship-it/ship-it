"""The integration test the review explicitly asked for, distinct from
test_human_reply_pauses_automation.py's direct `_capture_human_reply` call
(useful as a unit-level proof, but not integration):

    Realistic Evolution webhook JSON payload
      -> EvolutionProvider.parse_webhook (REAL)
      -> webhooks.whatsapp_webhook (REAL FastAPI route function, called
         directly with a minimal fake Request -- not a copy, not a stub
         of the dispatch logic)
      -> authorship decided from inbound.from_me (REAL)
      -> conversation_control.pause (REAL)
      -> revision incremented (REAL, verified in the real table)
      -> a stale claim_send is blocked (REAL, same fence
         test_pause_fencing.py already proves)

This is also the test that proves review finding (new, 2026-10-10):
EvolutionProvider.parse_webhook used to discard every fromMe=True event
(`or key.get("fromMe"): return None`), which made router.py's entire
owner-reply-capture path (it reads `inbound.from_me` to decide) dead code
-- regardless of settings, a real Evolution webhook for the owner's own
reply could never reach _capture_human_reply at all. Fixed in
providers/whatsapp/{evolution,baileys}/provider.py and base.py
(InboundMessage.from_me did not exist either).
"""

from __future__ import annotations

import json
import sys
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
    "repositories.base", "repositories.contact", "repositories.user", "repositories.message",
    "services.conversation_control", "providers.whatsapp.base",
    "providers.whatsapp.evolution.provider", "webhooks.router",
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
        load("mig_v1_webhook_int", BACKEND_ROOT / "alembic" / "versions" / "e610080001_pause_control.py"),
        load("mig_v2_webhook_int", BACKEND_ROOT / "alembic" / "versions" / "e610080002_review_delivery.py"),
    ]
    ctx = MigrationContext.configure(sync_conn)
    with Operations.context(ctx):
        for migration in migrations:
            migration.upgrade()


@pytest.fixture(scope="module", autouse=True)
def _real_modules():
    saved = {key: sys.modules.get(key) for key in _REAL_MODULE_KEYS}
    try:
        load_real_module("database.base", BACKEND_ROOT / "database" / "base.py")
        load_real_module("models.contact", BACKEND_ROOT / "models" / "contact.py")
        load_real_module("models.user", BACKEND_ROOT / "models" / "user.py")
        load_real_module("models.message", BACKEND_ROOT / "models" / "message.py")
        load_real_module("models.job", BACKEND_ROOT / "models" / "job.py")
        load_real_module("repositories.base", BACKEND_ROOT / "repositories" / "base.py")
        load_real_module("repositories.contact", BACKEND_ROOT / "repositories" / "contact.py")
        load_real_module("repositories.user", BACKEND_ROOT / "repositories" / "user.py")
        load_real_module("repositories.message", BACKEND_ROOT / "repositories" / "message.py")
        load_real_module("services.conversation_control", BACKEND_ROOT / "services" / "conversation_control.py")
        load_real_module("providers.whatsapp.base", BACKEND_ROOT / "providers" / "whatsapp" / "base.py")
        load_real_module(
            "providers.whatsapp.evolution.provider",
            BACKEND_ROOT / "providers" / "whatsapp" / "evolution" / "provider.py",
        )
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


@pytest.fixture
def evolution_provider_class(_real_modules):
    return sys.modules["providers.whatsapp.evolution.provider"].EvolutionProvider


@pytest_asyncio.fixture
async def real_db(_real_modules):
    Base = sys.modules["database.base"].Base
    User = sys.modules["models.user"].User
    UserRole = sys.modules["models.user"].UserRole
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_control_tables_sync)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    # _capture_human_reply only calls conversation_control.pause when
    # UserRepository.get_first_admin() finds someone -- a database with
    # no admin user silently skips the pause call instead of raising,
    # so this must be seeded or the fix would look broken when it isn't.
    async with sessions() as db:
        db.add(User(email="owner@example.com", full_name="Dário", hashed_password="x", role=UserRole.ADMIN))
        await db.commit()
    yield sessions
    await engine.dispose()


def _fake_request(raw_body: bytes):
    async def body():
        return raw_body

    return SimpleNamespace(body=body, headers={})


def _evolution_fromme_audio_payload(*, instance: str, client_jid: str, event_id: str) -> dict:
    """A realistic Evolution API "messages.upsert" webhook body for the
    owner replying with a voice note from his own phone -- fromMe=True,
    no transcribable text yet (exactly _capture_human_reply's
    personal_empty_audio case)."""
    return {
        "event": "messages.upsert",
        "instance": instance,
        "data": {
            "key": {"remoteJid": client_jid, "fromMe": True, "id": event_id},
            "pushName": "Dario",
            "message": {"audioMessage": {"seconds": 4, "mimetype": "audio/ogg; codecs=opus"}},
        },
    }


@pytest.mark.asyncio
async def test_real_evolution_fromme_payload_through_the_real_webhook_route_pauses_automation(
    router, conversation_control, evolution_provider_class, real_db,
):
    from utils.config import get_settings
    settings = get_settings()
    saved = {
        "webhook_secret": getattr(settings, "webhook_secret", ""),
        "evolution_personal_instance": settings.evolution_personal_instance,
        "evolution_base_url": getattr(settings, "evolution_base_url", None),
        "evolution_api_key": getattr(settings, "evolution_api_key", None),
        "stt_background_enabled": getattr(settings, "stt_background_enabled", None),
    }
    settings.webhook_secret = ""
    settings.evolution_personal_instance = "dario"
    settings.evolution_base_url = "http://localhost:0"
    settings.evolution_api_key = ""
    settings.stt_background_enabled = False
    try:
        provider = evolution_provider_class()
        original_get_provider = router.get_whatsapp_provider
        router.get_whatsapp_provider = lambda: provider
        try:
            payload = _evolution_fromme_audio_payload(
                instance="dario", client_jid="5511999990000@s.whatsapp.net", event_id="evt-webhook-int-1",
            )
            # Prove the parser itself produces from_me=True first -- this
            # is the exact thing that used to be impossible (the old
            # parse_webhook discarded this event and returned None).
            parsed = provider.parse_webhook(payload)
            assert parsed is not None
            assert parsed.from_me is True
            assert parsed.instance == "dario"

            raw_body = json.dumps(payload).encode()
            async with real_db() as db:
                ack = await router.whatsapp_webhook(_fake_request(raw_body), db)
            assert ack.status == "human_reply_captured"
        finally:
            router.get_whatsapp_provider = original_get_provider

        Contact = sys.modules["models.contact"].Contact
        async with real_db() as db:
            contact = (await db.execute(select(Contact).where(Contact.phone == "5511999990000"))).scalar_one()

        async with real_db() as db:
            row = (await db.execute(text(
                "SELECT paused, revision FROM conversation_controls WHERE contact_id=:cid AND instance=:inst"
            ), {"cid": contact.id, "inst": "dario"})).mappings().first()
        assert row is not None, "nenhuma linha de controle foi criada -- pause() nao foi acionado pelo webhook real"
        assert bool(row["paused"]) is True
        assert row["revision"] == 1

        # Tie-in with the already-proven fence: a send captured BEFORE
        # this webhook arrived, with the pre-webhook revision, must now
        # be blocked.
        async with real_db() as db:
            outcome = await conversation_control.claim_send(
                db, contact.id, "dario", 0, "twin-send:webhook-int-stale",
            )
            await db.commit()
        assert outcome == "suppressed"
    finally:
        for key, value in saved.items():
            setattr(settings, key, value)


def _evolution_fromme_text_payload(*, instance: str, client_jid: str, event_id: str, text_body: str) -> dict:
    """Same shape as the audio helper above, but a real TEXT fromMe event
    -- the branch that actually calls `find_unacknowledged_outbound` /
    `conversation_control.known_receipt` (the audio helper's
    `personal_empty_audio` case bypasses that logic entirely)."""
    return {
        "event": "messages.upsert",
        "instance": instance,
        "data": {
            "key": {"remoteJid": client_jid, "fromMe": True, "id": event_id},
            "pushName": "Dario",
            "message": {"conversation": text_body},
        },
    }


@pytest.mark.asyncio
async def test_real_evolution_fromme_text_payload_with_a_proven_receipt_is_captured_as_own_echo(
    router, conversation_control, evolution_provider_class, real_db,
):
    """The core regression this round fixes, through the FULL real path:
    JSON payload -> EvolutionProvider.parse_webhook (REAL) ->
    whatsapp_webhook (REAL) -> conversation_control.known_receipt (REAL)
    -> find_unacknowledged_outbound (REAL). A text fromMe event whose
    provider id is already a recorded receipt for OUR OWN send must be
    classified as an echo, attach the id to that row, and must NOT pause."""
    from utils.config import get_settings
    settings = get_settings()
    saved = {
        "webhook_secret": getattr(settings, "webhook_secret", ""),
        "evolution_personal_instance": settings.evolution_personal_instance,
        "evolution_base_url": getattr(settings, "evolution_base_url", None),
        "evolution_api_key": getattr(settings, "evolution_api_key", None),
        "stt_background_enabled": getattr(settings, "stt_background_enabled", None),
    }
    settings.webhook_secret = ""
    settings.evolution_personal_instance = "dario"
    settings.evolution_base_url = "http://localhost:0"
    settings.evolution_api_key = ""
    settings.stt_background_enabled = False
    try:
        provider = evolution_provider_class()
        original_get_provider = router.get_whatsapp_provider
        router.get_whatsapp_provider = lambda: provider
        try:
            Message = sys.modules["models.message"].Message
            MessageDirection = sys.modules["models.message"].MessageDirection
            Contact = sys.modules["models.contact"].Contact
            async with real_db() as db:
                contact = Contact(name="Cliente Eco", phone="5511966665555")
                db.add(contact)
                await db.commit()
                await db.refresh(contact)
                contact_id = contact.id
                sent = Message(
                    contact_id=contact_id, direction=MessageDirection.OUTBOUND,
                    content="Separado, te mando o boleto.", is_autopilot_reply=True,
                    whatsapp_instance="dario",
                )
                db.add(sent)
                await db.commit()
                await db.refresh(sent)
                sent_id = sent.id

            async with real_db() as db:
                await conversation_control.record_receipt(db, contact_id, "dario", "evt-webhook-echo-1")
                await db.commit()

            payload = _evolution_fromme_text_payload(
                instance="dario", client_jid="5511966665555@s.whatsapp.net",
                event_id="evt-webhook-echo-1", text_body="Separado, te mando o boleto.",
            )
            raw_body = json.dumps(payload).encode()
            async with real_db() as db:
                ack = await router.whatsapp_webhook(_fake_request(raw_body), db)
        finally:
            router.get_whatsapp_provider = original_get_provider

        assert ack.status == "own_echo"
        assert ack.message_id == sent_id

        async with real_db() as db:
            row = (await db.execute(text(
                "SELECT paused FROM conversation_controls WHERE contact_id=:cid AND instance=:inst"
            ), {"cid": contact_id, "inst": "dario"})).mappings().first()
        assert row is None, "o eco real via webhook pausou a automacao"
    finally:
        for key, value in saved.items():
            setattr(settings, key, value)


@pytest.mark.asyncio
async def test_real_evolution_fromme_text_payload_matching_old_unconfirmed_send_is_still_human(
    router, evolution_provider_class, real_db,
):
    """Same regression, through the FULL real path: a human typing the
    exact words of an old, never-acknowledged autopilot send, with NO
    receipt ever recorded for this event's provider id, must still be
    captured as a real human reply and pause automation."""
    from utils.config import get_settings
    settings = get_settings()
    saved = {
        "webhook_secret": getattr(settings, "webhook_secret", ""),
        "evolution_personal_instance": settings.evolution_personal_instance,
        "evolution_base_url": getattr(settings, "evolution_base_url", None),
        "evolution_api_key": getattr(settings, "evolution_api_key", None),
        "stt_background_enabled": getattr(settings, "stt_background_enabled", None),
    }
    settings.webhook_secret = ""
    settings.evolution_personal_instance = "dario"
    settings.evolution_base_url = "http://localhost:0"
    settings.evolution_api_key = ""
    settings.stt_background_enabled = False
    try:
        provider = evolution_provider_class()
        original_get_provider = router.get_whatsapp_provider
        router.get_whatsapp_provider = lambda: provider
        try:
            Message = sys.modules["models.message"].Message
            MessageDirection = sys.modules["models.message"].MessageDirection
            Contact = sys.modules["models.contact"].Contact
            async with real_db() as db:
                contact = Contact(name="Cliente Colisao", phone="5511955554444")
                db.add(contact)
                await db.commit()
                await db.refresh(contact)
                contact_id = contact.id
                stale = Message(
                    contact_id=contact_id, direction=MessageDirection.OUTBOUND,
                    content="Oi, tudo bem?", is_autopilot_reply=True, whatsapp_instance="dario",
                )
                db.add(stale)
                await db.commit()
                await db.refresh(stale)
                stale_id = stale.id

            payload = _evolution_fromme_text_payload(
                instance="dario", client_jid="5511955554444@s.whatsapp.net",
                event_id="evt-webhook-collision-1", text_body="Oi, tudo bem?",
            )
            raw_body = json.dumps(payload).encode()
            async with real_db() as db:
                ack = await router.whatsapp_webhook(_fake_request(raw_body), db)
        finally:
            router.get_whatsapp_provider = original_get_provider

        assert ack.status == "human_reply_captured"
        assert ack.message_id != stale_id

        async with real_db() as db:
            old_message = (await db.execute(select(Message).where(Message.id == stale_id))).scalar_one()
            row = (await db.execute(text(
                "SELECT paused FROM conversation_controls WHERE contact_id=:cid AND instance=:inst"
            ), {"cid": contact_id, "inst": "dario"})).mappings().first()
        assert old_message.external_id is None
        assert row is not None and bool(row["paused"]) is True
    finally:
        for key, value in saved.items():
            setattr(settings, key, value)


@pytest.mark.asyncio
async def test_duplicate_webhook_delivery_of_the_same_event_is_not_double_processed(
    router, evolution_provider_class, real_db,
):
    """Idempotency: a redelivered webhook for the SAME event_id must not
    create a second message or pause the conversation twice (the unique
    constraint on messages.external_id, checked explicitly earlier in
    whatsapp_webhook, is what the review asked to see actually exercised
    for this path -- not just assumed)."""
    from utils.config import get_settings
    settings = get_settings()
    saved_personal = settings.evolution_personal_instance
    saved_webhook_secret = getattr(settings, "webhook_secret", "")
    saved_base_url = getattr(settings, "evolution_base_url", None)
    saved_api_key = getattr(settings, "evolution_api_key", None)
    saved_stt = getattr(settings, "stt_background_enabled", None)
    settings.webhook_secret = ""
    settings.evolution_personal_instance = "dario"
    settings.evolution_base_url = "http://localhost:0"
    settings.evolution_api_key = ""
    settings.stt_background_enabled = False
    try:
        provider = evolution_provider_class()
        original_get_provider = router.get_whatsapp_provider
        router.get_whatsapp_provider = lambda: provider
        try:
            payload = _evolution_fromme_audio_payload(
                instance="dario", client_jid="5511988887777@s.whatsapp.net", event_id="evt-duplicate-1",
            )
            raw_body = json.dumps(payload).encode()

            async with real_db() as db:
                first_ack = await router.whatsapp_webhook(_fake_request(raw_body), db)
            async with real_db() as db:
                second_ack = await router.whatsapp_webhook(_fake_request(raw_body), db)
        finally:
            router.get_whatsapp_provider = original_get_provider

        assert first_ack.status == "human_reply_captured"
        # own_echo or duplicate are both acceptable "did not create a
        # second row" outcomes for a redelivered fromMe event -- what
        # matters is it is NOT a second "human_reply_captured" creating a
        # second message, and the message id is the same.
        assert second_ack.status in ("duplicate", "own_echo")
        assert second_ack.message_id == first_ack.message_id

        async with real_db() as db:
            count = (await db.execute(text(
                "SELECT count(*) FROM messages WHERE external_id = 'evt-duplicate-1'"
            ))).scalar_one()
        assert count == 1
    finally:
        settings.evolution_personal_instance = saved_personal
        settings.webhook_secret = saved_webhook_secret
        settings.evolution_base_url = saved_base_url
        settings.evolution_api_key = saved_api_key
        settings.stt_background_enabled = saved_stt


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
