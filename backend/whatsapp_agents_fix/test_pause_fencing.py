"""Proof, against the REAL services/conversation_control.py and a REAL
SQLite database (migrated with the real Alembic revisions this package
ships -- see conftest.py), that human pause:

  1. blocks a NEW autopilot reply generated after the pause (the obvious
     case -- `twin_autopilot_check`'s own `snapshot` check before
     generating);
  2. blocks a message that was ALREADY ENQUEUED before the pause
     happened -- the case the review specifically asked to confirm. This
     is the scenario that matters: `twin_autopilot_check` captures
     `revision` once, at the start, and puts it in the job payload
     (`_twin_revision`). The job then sits in the queue for
     `whatsapp_twin_idle_timeout_seconds` (or longer, under load) before
     `send_whatsapp_text` actually runs. If a human replies during that
     wait, the job is still sitting there with the OLD revision baked in
     -- this file proves `claim_send` (called inside `send_whatsapp_text`
     right before transport, per handlers.py.diff) rejects it, using the
     exact mechanism (optimistic revision fencing inside the database),
     not a mock of it;
  3. blocks EVERY already-queued message from a backlog, not just the
     next one -- a human taking over mid-conversation often has several
     client messages already queued for auto-reply;
  4. does not retroactively "unstick" an old queued send after resume --
     resume starts a fresh revision for FUTURE sends only; a message
     queued under the old revision stays suppressed even after resume,
     because its captured revision can never match the new one;
  5. does let a genuinely NEW message (generated after resume, carrying
     the new revision) go through normally -- pause is not "stuck
     forever".

No mocks of conversation_control anywhere in this file -- the same
module copied verbatim from the V2 candidate, the same migrations, same
pattern as test_incident_dedup.py's real-store tests.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_queued_message_is_blocked_when_human_takes_over_before_it_sends(real_control_db):
    control, sessions = real_control_db

    # 1. twin_autopilot_check starts: snapshot the current revision (0,
    #    fresh contact) and capture it -- this is what gets baked into
    #    the job payload as `_twin_revision`.
    async with sessions() as db:
        snap = await control.snapshot(db, 42, "dario")
    captured_revision = snap["revision"]
    assert captured_revision == 0
    assert snap["paused"] is False

    # 2. The job is now "in the queue" (conceptually -- nothing else
    #    happens here, exactly like a real job sitting with
    #    delay_seconds=whatsapp_twin_idle_timeout_seconds before it runs).
    #    While it waits, a human (the owner or an attendant) replies.
    async with sessions() as db:
        paused_state = await control.pause(db, 42, "dario", event_id="human-reply-1", reason="owner_replied", actor_id=7)
        await db.commit()
    assert paused_state["paused"] is True
    assert paused_state["revision"] == 1  # bumped -- no longer 0

    # 3. The queued job finally runs: send_whatsapp_text calls claim_send
    #    with the STALE revision captured in step 1 (0), exactly as
    #    handlers.py.diff does via payload['_twin_revision'].
    async with sessions() as db:
        outcome = await control.claim_send(db, 42, "dario", captured_revision, "twin-send:42:dario:9212")
        await db.commit()

    assert outcome == "suppressed"  # the already-queued message is blocked


@pytest.mark.asyncio
async def test_entire_backlog_of_queued_messages_is_blocked_not_just_the_next_one(real_control_db):
    control, sessions = real_control_db

    # Simulate 3 messages already queued (3 separate twin_autopilot_check
    # runs that all completed and enqueued a send job) BEFORE the pause --
    # all captured the same pre-pause revision.
    async with sessions() as db:
        snap = await control.snapshot(db, 42, "dario")
    captured_revision = snap["revision"]
    queued_intents = ["twin-send:42:dario:100", "twin-send:42:dario:101", "twin-send:42:dario:102"]

    async with sessions() as db:
        await control.pause(db, 42, "dario", event_id="human-reply-backlog", reason="owner_replied", actor_id=7)
        await db.commit()

    outcomes = []
    for intent_id in queued_intents:
        async with sessions() as db:
            outcomes.append(await control.claim_send(db, 42, "dario", captured_revision, intent_id))
            await db.commit()

    assert outcomes == ["suppressed", "suppressed", "suppressed"]


@pytest.mark.asyncio
async def test_resume_does_not_retroactively_unstick_an_old_queued_send(real_control_db):
    control, sessions = real_control_db

    async with sessions() as db:
        snap = await control.snapshot(db, 42, "dario")
    stale_revision = snap["revision"]

    async with sessions() as db:
        paused = await control.pause(db, 42, "dario", event_id="e1", reason="owner_replied", actor_id=7)
        await db.commit()

    async with sessions() as db:
        resumed = await control.resume(db, 42, "dario", paused["revision"], actor_id=7)
        await db.commit()
    assert resumed["paused"] is False
    assert resumed["revision"] != stale_revision

    # The message queued BEFORE the pause, still carrying the original
    # stale revision, must stay suppressed even though the conversation
    # is unpaused again -- its captured revision can never match the
    # post-resume revision. This is what stops a slow worker from
    # "escaping" a reply that was correctly invalidated.
    async with sessions() as db:
        outcome = await control.claim_send(db, 42, "dario", stale_revision, "twin-send:42:dario:old")
        await db.commit()
    assert outcome == "suppressed"


@pytest.mark.asyncio
async def test_a_genuinely_new_message_after_resume_sends_normally(real_control_db):
    control, sessions = real_control_db

    async with sessions() as db:
        paused = await control.pause(db, 42, "dario", event_id="e1", reason="owner_replied", actor_id=7)
        await db.commit()
    async with sessions() as db:
        await control.resume(db, 42, "dario", paused["revision"], actor_id=7)
        await db.commit()

    # A NEW twin_autopilot_check run, starting after resume, captures the
    # CURRENT (post-resume) revision -- this one must be allowed through.
    async with sessions() as db:
        fresh_snap = await control.snapshot(db, 42, "dario")
    async with sessions() as db:
        outcome = await control.claim_send(db, 42, "dario", fresh_snap["revision"], "twin-send:42:dario:new")
        await db.commit()
    assert outcome == "claimed"


@pytest.mark.asyncio
async def test_pause_mid_generation_blocks_the_send_attempted_right_after(real_control_db):
    # Models the exact handlers.py flow: revision captured before an
    # (here, simulated) slow LLM call; pause happens WHILE that call is
    # running; the send attempted right after still gets the stale
    # revision and is blocked by claim_send -- not by any check that
    # happened to run before the pause.
    control, sessions = real_control_db

    async with sessions() as db:
        snap = await control.snapshot(db, 42, "dario")
    captured_revision = snap["revision"]

    async def slow_generation():
        await asyncio.sleep(0.01)
        return "resposta gerada"

    async def pause_mid_flight():
        await asyncio.sleep(0.005)
        async with sessions() as db:
            await control.pause(db, 42, "dario", event_id="mid-flight", reason="owner_replied", actor_id=7)
            await db.commit()

    reply, _ = await asyncio.gather(slow_generation(), pause_mid_flight())
    assert reply == "resposta gerada"  # generation itself is not aborted...

    # ...but the send attempt right after it, still carrying the revision
    # captured before generation started, is blocked.
    async with sessions() as db:
        outcome = await control.claim_send(db, 42, "dario", captured_revision, "twin-send:42:dario:midflight")
        await db.commit()
    assert outcome == "suppressed"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
