"""Real execution of the REAL, patched `send_whatsapp_text` -- loaded by
its actual deployed path (backend/jobs/handlers.py), not a copy, not
re-typed, not AST-inspected -- against a REAL SQLite database migrated
with the REAL Alembic revisions, proving the configured-fake WhatsApp
provider receives ZERO calls under each of three blocking conditions the
review asked to confirm:

  1. pausa ativa (human took over before this specific send was attempted)
  2. mensagem antiga na fila (revision captured before a pause that
     happened while the message was queued)
  3. marcador interno (output_safe's content barrier)

Everything imported by jobs/handlers.py that this delivery did not
receive as source (ORM repositories, job queue, provider factory, audit
log, settings) is a minimal FAKE in app_stub/ -- each file there says so
in its own docstring. What is NOT fake, and NOT a copy: `jobs/handlers.py`
and `services/conversation_control.py` are both loaded by
`conftest.py`'s `load_real_module` directly from their real,
canonically-deployed paths under backend/ -- there is no static copy of
either anywhere in this review package to drift from what actually
ships.

AST-only proof (test_handlers_integration.py) and SQLite-only logic proof
(test_incident_dedup.py / test_pause_fencing.py, which call
conversation_control functions directly) do NOT demonstrate that the real
`send_whatsapp_text` control flow actually reaches those functions and
stops before the provider. This file is what does.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import load_real_module

HERE = Path(__file__).parent
BACKEND_ROOT = HERE.parents[0]
APP_STUB = str(HERE / "app_stub")
if APP_STUB not in sys.path:
    sys.path.insert(0, APP_STUB)

# Real deployed files, loaded by their actual path -- jobs.handlers'
# own `from services.output_safety import output_safe` resolves against
# the real file registered here under that name too, not app_stub's
# (there is no copy of output_safety.py left in app_stub/ for this
# reason -- see conftest.py's load_real_module docstring).
load_real_module("services.output_safety", BACKEND_ROOT / "services" / "output_safety.py")
conversation_control = load_real_module("services.conversation_control", BACKEND_ROOT / "services" / "conversation_control.py")
handlers = load_real_module("jobs.handlers", BACKEND_ROOT / "jobs" / "handlers.py")

from providers.whatsapp.fake_provider import FAKE_PROVIDER  # noqa: E402

REAL_MARKER = "[Áudio enviado pelo proprietário desta conta nesta conversa]"


@pytest.fixture(autouse=True)
def _reset_fake_provider():
    FAKE_PROVIDER.reset()
    yield
    FAKE_PROVIDER.reset()


@pytest.mark.asyncio
async def test_pause_active_before_send_blocks_the_provider(real_control_db):
    _, sessions = real_control_db
    async with sessions() as db:
        snap = await conversation_control.snapshot(db, 42, "dario")
        revision = snap["revision"]

    async with sessions() as db:
        await conversation_control.pause(db, 42, "dario", event_id="e-pause-1", reason="owner_replied", actor_id=7)
        await db.commit()

    payload = {
        "to": "+5511999990000", "content": "Resposta automática normal",
        "is_autopilot_reply": True, "instance": "dario",
        "_twin_contact_id": 42, "_twin_source_message_id": 9001, "_twin_revision": revision,
    }
    async with sessions() as db:
        await handlers.send_whatsapp_text(db, payload)

    assert FAKE_PROVIDER.calls == []


@pytest.mark.asyncio
async def test_old_queued_message_blocks_the_provider_when_the_job_finally_runs(real_control_db):
    """The job that was sitting in the queue (captured revision 0) only
    actually calls send_whatsapp_text NOW, after the human already
    replied -- the exact scenario the review asked to confirm."""
    _, sessions = real_control_db
    async with sessions() as db:
        snap = await conversation_control.snapshot(db, 42, "dario")
        stale_revision = snap["revision"]  # captured when the job was enqueued

    async with sessions() as db:
        await conversation_control.pause(db, 42, "dario", event_id="e-pause-2", reason="owner_replied", actor_id=7)
        await db.commit()

    payload = {
        "to": "+5511999990000", "content": "Oi! Aqui é o assistente automático do Dário.",
        "is_autopilot_reply": True, "instance": "dario",
        "_twin_contact_id": 42, "_twin_source_message_id": 9002, "_twin_revision": stale_revision,
    }
    async with sessions() as db:
        await handlers.send_whatsapp_text(db, payload)

    assert FAKE_PROVIDER.calls == []


@pytest.mark.asyncio
async def test_internal_marker_blocks_the_provider_even_with_no_pause_at_all(real_control_db):
    """No pause involved at all -- proves output_safe's barrier is
    independent of the pause/claim_send mechanism, exactly as designed
    (two different protections, neither a substitute for the other)."""
    _, sessions = real_control_db
    payload = {
        "to": "+5511999990000",
        "content": f"{REAL_MARKER}\nClaro, posso te ajudar com isso!",
        "instance": "dario",
    }
    async with sessions() as db:
        await handlers.send_whatsapp_text(db, payload)

    assert FAKE_PROVIDER.calls == []


@pytest.mark.asyncio
async def test_internal_marker_blocks_even_when_also_carrying_a_valid_revision(real_control_db):
    """Content barrier and pause fencing are independent checks -- a
    message that WOULD pass claim_send (fresh revision, not paused) must
    still be blocked if it also contains the internal marker."""
    _, sessions = real_control_db
    async with sessions() as db:
        snap = await conversation_control.snapshot(db, 42, "dario")
        fresh_revision = snap["revision"]

    payload = {
        "to": "+5511999990000",
        "content": f"{REAL_MARKER}\nO produto está disponível, sim.",
        "is_autopilot_reply": True, "instance": "dario",
        "_twin_contact_id": 42, "_twin_source_message_id": 9003, "_twin_revision": fresh_revision,
    }
    async with sessions() as db:
        await handlers.send_whatsapp_text(db, payload)

    assert FAKE_PROVIDER.calls == []


@pytest.mark.asyncio
async def test_control_group_an_ordinary_unpaused_fresh_message_DOES_reach_the_provider(real_control_db):
    """Negative control: proves the test harness itself is not just
    silently failing to call send_whatsapp_text at all -- an ordinary
    message, not paused, fresh revision, no marker, must actually reach
    the (fake) provider exactly once."""
    _, sessions = real_control_db
    async with sessions() as db:
        snap = await conversation_control.snapshot(db, 42, "dario")
        fresh_revision = snap["revision"]

    payload = {
        "to": "+5511999990000", "content": "Oi! Temos o thinner 5L disponível, R$ 45,00.",
        "is_autopilot_reply": True, "instance": "dario",
        "_twin_contact_id": 42, "_twin_source_message_id": 9004, "_twin_revision": fresh_revision,
    }
    async with sessions() as db:
        await handlers.send_whatsapp_text(db, payload)

    assert FAKE_PROVIDER.calls == [("send_text", "+5511999990000", "Oi! Temos o thinner 5L disponível, R$ 45,00.", None)]


@pytest.mark.asyncio
async def test_successful_send_captures_the_real_receipt_and_promotes_to_sent(real_control_db):
    """Review fix (C): a provider response with a recognizable receipt
    (response["key"]["id"], the real Baileys/Evolution API shape) must
    promote the send intent to 'sent' -- before this fix, `finish_send`
    was always called with a hardcoded None, so even a successful send
    stayed stuck at 'needs_review' forever."""
    _, sessions = real_control_db
    async with sessions() as db:
        fresh_revision = (await conversation_control.snapshot(db, 42, "dario"))["revision"]

    payload = {
        "to": "+5511999990000", "content": "Oi! Temos o thinner 5L disponível, R$ 45,00.",
        "is_autopilot_reply": True, "instance": "dario",
        "_twin_contact_id": 42, "_twin_source_message_id": 9005, "_twin_revision": fresh_revision,
    }
    async with sessions() as db:
        await handlers.send_whatsapp_text(db, payload)

    intent_id = "twin-send:42:dario:9005"
    async with sessions() as db:
        row = await conversation_control._one(
            db, "SELECT status, receipt_id FROM conversation_send_intents WHERE id=:id", {"id": intent_id},
        )
    assert row["status"] == "sent"
    assert row["receipt_id"] == "FAKE-RECEIPT-1"


@pytest.mark.asyncio
async def test_a_plain_non_twin_send_leaves_a_durable_receipt_so_its_own_echo_is_never_a_human_takeover(real_control_db):
    """Round 6 regression guard. Before this change only the Twin's
    send_intent path recorded receipts, so a store/B2B/Azusa send's fromMe
    echo had no proof and webhooks/router.py treated it as a human reply
    -- pausing the very conversation the bot was handling. Every send with
    a recognized receipt must now leave a conversation_receipts row scoped
    to the instance its echo will carry back."""
    _, sessions = real_control_db
    payload = {
        "to": "+5511999990000", "content": "Temos o thinner 5L, R$ 45,00.",
        "instance": "store",
    }
    async with sessions() as db:
        await handlers.send_whatsapp_text(db, payload)

    async with sessions() as db:
        row = await conversation_control._one(
            db,
            "SELECT COUNT(*) AS n FROM conversation_receipts WHERE instance=:inst AND external_id=:ext",
            {"inst": "store", "ext": "FAKE-RECEIPT-1"},
        )
    assert row["n"] == 1


@pytest.mark.asyncio
async def test_receipt_is_durable_even_when_the_later_persistence_step_fails(real_control_db, monkeypatch):
    """Round 6 ordering guard. The receipt must be committed right after the
    transport returns, not after persist_outbound_message's bookkeeping. If
    that bookkeeping fails, the send already happened, so the receipt must
    still exist for its echo to be recognized."""
    _, sessions = real_control_db

    async def failing_persist(db, to, content, **kwargs):
        raise RuntimeError("simulated failure in persistence after transport")

    monkeypatch.setattr(handlers, "persist_outbound_message", failing_persist)
    payload = {"to": "+5511999990000", "content": "Oi, segue o orcamento.", "instance": "store"}
    async with sessions() as db:
        with pytest.raises(RuntimeError):
            await handlers.send_whatsapp_text(db, payload)

    async with sessions() as db:
        row = await conversation_control._one(
            db,
            "SELECT COUNT(*) AS n FROM conversation_receipts WHERE instance=:inst AND external_id=:ext",
            {"inst": "store", "ext": "FAKE-RECEIPT-1"},
        )
    assert row["n"] == 1


@pytest.mark.asyncio
async def test_unrecognized_provider_response_stays_needs_review_not_promoted_on_a_guess(real_control_db):
    """The flip side of the test above: a provider response that doesn't
    have the recognized key.id shape (here, None -- the old FAKE_PROVIDER
    default, and what an unknown/future provider might still return) must
    NOT be promoted to 'sent'. Acceptance by the provider is not proof of
    anything without a real, recognized receipt."""
    _, sessions = real_control_db
    async with sessions() as db:
        fresh_revision = (await conversation_control.snapshot(db, 42, "dario"))["revision"]

    FAKE_PROVIDER.simulated_response = None
    payload = {
        "to": "+5511999990000", "content": "Mensagem de teste",
        "is_autopilot_reply": True, "instance": "dario",
        "_twin_contact_id": 42, "_twin_source_message_id": 9008, "_twin_revision": fresh_revision,
    }
    async with sessions() as db:
        await handlers.send_whatsapp_text(db, payload)

    intent_id = "twin-send:42:dario:9008"
    async with sessions() as db:
        row = await conversation_control._one(
            db, "SELECT status FROM conversation_send_intents WHERE id=:id", {"id": intent_id},
        )
    assert row["status"] == "needs_review"


@pytest.mark.asyncio
async def test_claim_is_committed_before_transport_so_a_crash_during_send_cannot_cause_a_resend(real_control_db):
    """Review fix (A): conversation_control.py's own module docstring
    requires the claim to be committed BEFORE transport ("Callers must
    COMMIT a successful claim before transport"). Simulated by making the
    fake provider raise mid-call, standing in for a crash/timeout during
    the real network call -- the claim must already be durably committed
    at that point, so a retry's claim_send sees this intent already
    reserved (not 'claimed' again) and refuses to resend."""
    _, sessions = real_control_db
    async with sessions() as db:
        fresh_revision = (await conversation_control.snapshot(db, 42, "dario"))["revision"]

    payload = {
        "to": "+5511999990000", "content": "Mensagem de teste",
        "is_autopilot_reply": True, "instance": "dario",
        "_twin_contact_id": 42, "_twin_source_message_id": 9007, "_twin_revision": fresh_revision,
    }

    original_send_text = FAKE_PROVIDER.send_text

    async def crash_during_transport(to, content, instance=None):
        FAKE_PROVIDER.calls.append(("send_text", to, content, instance))
        raise RuntimeError("simulated crash during transport")

    FAKE_PROVIDER.send_text = crash_during_transport
    try:
        async with sessions() as db:
            with pytest.raises(RuntimeError):
                await handlers.send_whatsapp_text(db, payload)
    finally:
        FAKE_PROVIDER.send_text = original_send_text

    assert len(FAKE_PROVIDER.calls) == 1  # the one call, right before the simulated crash

    # Retry in a FRESH session -- exactly what a worker reclaim/retry does
    # after a crash. Before fix (A), the claim from the first attempt was
    # never committed, so this would have claimed again and sent a second
    # time.
    async with sessions() as db:
        await handlers.send_whatsapp_text(db, payload)

    assert len(FAKE_PROVIDER.calls) == 1  # still just the one call -- no resend


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
