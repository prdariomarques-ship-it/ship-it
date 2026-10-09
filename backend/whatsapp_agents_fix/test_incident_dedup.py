"""Regression tests for incident_dedup.py.

Two distinct levels, per the review's explicit instruction to separate
"testes de lógica pura/fakes" from real persistence/concurrency proof:

  - TestDecideOwnerAlertContract: pure logic, a minimal fake in place of
    conversation_control, proving decide_owner_alert computes the right
    key and calls alert_claim with it -- NOT a storage implementation,
    just a call-contract check. No DB.

  - TestRealConversationControlIntegration: the REAL
    services/conversation_control.py (copied verbatim from the V2
    candidate -- see DELIVERY_NOTES.md), a REAL SQLite database created
    from the REAL Alembic migrations in alembic/versions/, and REAL
    concurrent asyncio tasks racing the same claim. This is what actually
    proves incident_dedup.py's dedup_key design (paraphrase collapsing,
    message-id independence, window rollover) survives contact with a
    real transactional store, not just a mock.

conversation_control.py's OWN test suites (run separately, see
DELIVERY_NOTES.md) already prove its internals -- pause/resume fencing,
concurrent claim_send, close_unknown races -- against both real SQLite
(38 tests) and a real local PostgreSQL 16 server (1 opt-in test,
actually executed in this sandbox, not skipped). This file does not
repeat that; it only proves THIS module's dedup_key logic composes
correctly with the real thing.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from incident_dedup import AlertDecision, decide_owner_alert, dedup_key, evidence_group
from twin_risk_gate import MessageAuthor, RiskEvidence

NOW = datetime(2026, 10, 8, 15, 19, 0, tzinfo=timezone.utc)


def _evidence(category: str = "crise", snippet: str = "culpa") -> RiskEvidence:
    return RiskEvidence(
        category=category, snippet=snippet, source_message_id=1,
        source_author=MessageAuthor.CLIENT, source_created_at=NOW, in_current_message=False,
    )


# ---------------------------------------------------------------------------
# Pure logic: dedup_key / evidence_group, no DB, no fake even needed.
# ---------------------------------------------------------------------------

def test_dedup_key_excludes_message_id_by_construction():
    # There is no message_id parameter at all -- a new id carrying the
    # same evidence cannot produce a different key.
    import inspect
    assert "message_id" not in inspect.signature(dedup_key).parameters


def test_dedup_key_same_inputs_same_key():
    a = dedup_key(contact_id=1, instance="dario", category="crise", group="culpa", now=NOW, window_seconds=3600)
    b = dedup_key(contact_id=1, instance="dario", category="crise", group="culpa", now=NOW, window_seconds=3600)
    assert a == b


@pytest.mark.parametrize("field,other", [
    ("contact_id", 2), ("instance", "other"), ("category", "negocio"), ("group", "medo"),
])
def test_dedup_key_changes_with_each_dimension(field, other):
    base = dict(contact_id=1, instance="dario", category="crise", group="culpa", now=NOW, window_seconds=3600)
    changed = dict(base, **{field: other})
    assert dedup_key(**base) != dedup_key(**changed)


def test_dedup_key_rolls_over_to_a_new_bucket_after_the_window():
    from datetime import timedelta
    base = dict(contact_id=1, instance="dario", category="crise", group="culpa", window_seconds=3600)
    first = dedup_key(now=NOW, **base)
    later = dedup_key(now=NOW + timedelta(hours=2), **base)
    assert first != later  # same evidence, but the window elapsed -- must be allowed to re-arm


def test_dedup_key_stable_within_the_same_window():
    from datetime import timedelta
    base = dict(contact_id=1, instance="dario", category="crise", group="culpa", window_seconds=3600)
    first = dedup_key(now=NOW, **base)
    soon_after = dedup_key(now=NOW + timedelta(minutes=5), **base)
    assert first == soon_after


def test_evidence_group_uses_paraphrase_grouping_for_crise():
    crying = _evidence(category="crise", snippet="chorei")
    crying_again = _evidence(category="crise", snippet="chorando")
    assert evidence_group(crying) == evidence_group(crying_again)


def test_evidence_group_passes_through_non_crise_categories():
    assert evidence_group(_evidence(category="negocio", snippet="venda")) == "negocio"
    assert evidence_group(_evidence(category="loop", snippet="loop_guard")) == "loop"


# ---------------------------------------------------------------------------
# Pure call-contract test with a minimal fake -- NOT a storage
# implementation, just proves decide_owner_alert calls alert_claim with
# the key it computed and relays the result.
# ---------------------------------------------------------------------------

class _FakeConversationControl:
    """Records calls; does not persist anything -- this is a test double
    for THIS file's contract tests only, never wired into handlers.py."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str]] = []
        self.claimed: set[str] = set()

    async def alert_claim(self, db, contact_id, instance, key):
        self.calls.append((contact_id, instance, key))
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True


@pytest.mark.asyncio
async def test_decide_owner_alert_calls_alert_claim_with_the_computed_key():
    control = _FakeConversationControl()
    decision = await decide_owner_alert(
        control, db=None, contact_id=42, instance="dario", evidence=_evidence(), window_seconds=3600, now=NOW,
    )
    assert decision.should_alert is True
    assert control.calls == [(42, "dario", decision.key)]


@pytest.mark.asyncio
async def test_decide_owner_alert_relays_false_when_already_claimed():
    control = _FakeConversationControl()
    first = await decide_owner_alert(control, db=None, contact_id=42, instance="dario", evidence=_evidence(), window_seconds=3600, now=NOW)
    second = await decide_owner_alert(control, db=None, contact_id=42, instance="dario", evidence=_evidence(), window_seconds=3600, now=NOW)
    assert first.should_alert is True
    assert second.should_alert is False
    assert first.key == second.key


# ---------------------------------------------------------------------------
# Real integration: the actual services/conversation_control.py, a real
# SQLite database built from the actual Alembic migrations.
# `real_control_db` fixture is shared via conftest.py (also used by
# test_pause_fencing.py).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_real_store_suppresses_the_exact_9212_scenario(real_control_db):
    # The real incident: four "culpa" readings minutes apart must produce
    # exactly one alert against the real store.
    control, sessions = real_control_db
    evidence = _evidence(snippet="culpa")
    results = []
    for _ in range(4):
        async with sessions() as db:
            decision = await decide_owner_alert(control, db, contact_id=42, instance="dario", evidence=evidence, window_seconds=3600, now=NOW)
            await db.commit()
            results.append(decision.should_alert)
    assert results == [True, False, False, False]


@pytest.mark.asyncio
async def test_real_store_new_message_id_same_evidence_does_not_reopen(real_control_db):
    control, sessions = real_control_db
    evidence_a = RiskEvidence("crise", "culpa", 9212, MessageAuthor.CLIENT, NOW, False)
    evidence_b = RiskEvidence("crise", "culpa", 9400, MessageAuthor.CLIENT, NOW, False)  # new id, same content
    async with sessions() as db:
        first = await decide_owner_alert(control, db, contact_id=42, instance="dario", evidence=evidence_a, window_seconds=3600, now=NOW)
        await db.commit()
    async with sessions() as db:
        second = await decide_owner_alert(control, db, contact_id=42, instance="dario", evidence=evidence_b, window_seconds=3600, now=NOW)
        await db.commit()
    assert first.should_alert is True
    assert second.should_alert is False


@pytest.mark.asyncio
async def test_real_store_genuinely_new_evidence_still_escalates(real_control_db):
    control, sessions = real_control_db
    mild = _evidence(snippet="culpa")
    severe = _evidence(snippet="suicidio")
    async with sessions() as db:
        first = await decide_owner_alert(control, db, contact_id=42, instance="dario", evidence=mild, window_seconds=3600, now=NOW)
        await db.commit()
    async with sessions() as db:
        second = await decide_owner_alert(control, db, contact_id=42, instance="dario", evidence=severe, window_seconds=3600, now=NOW)
        await db.commit()
    assert first.should_alert is True
    assert second.should_alert is True  # different, more severe group -- must still escalate


@pytest.mark.asyncio
async def test_real_store_paraphrase_of_same_evidence_does_not_reescalate(real_control_db):
    control, sessions = real_control_db
    crying = _evidence(snippet="chorei")
    crying_paraphrased = _evidence(snippet="chorando")
    async with sessions() as db:
        first = await decide_owner_alert(control, db, contact_id=42, instance="dario", evidence=crying, window_seconds=3600, now=NOW)
        await db.commit()
    async with sessions() as db:
        second = await decide_owner_alert(control, db, contact_id=42, instance="dario", evidence=crying_paraphrased, window_seconds=3600, now=NOW)
        await db.commit()
    assert first.should_alert is True
    assert second.should_alert is False  # same underlying statement, reworded


@pytest.mark.asyncio
async def test_real_store_window_rollover_allows_a_fresh_alert(real_control_db):
    from datetime import timedelta
    control, sessions = real_control_db
    evidence = _evidence(snippet="culpa")
    async with sessions() as db:
        first = await decide_owner_alert(control, db, contact_id=42, instance="dario", evidence=evidence, window_seconds=3600, now=NOW)
        await db.commit()
    async with sessions() as db:
        second = await decide_owner_alert(control, db, contact_id=42, instance="dario", evidence=evidence, window_seconds=3600, now=NOW + timedelta(hours=2))
        await db.commit()
    assert first.should_alert is True
    assert second.should_alert is True  # same evidence, but not suppressed forever


@pytest.mark.asyncio
async def test_real_store_concurrent_identical_claims_only_one_wins(real_control_db):
    # Real concurrent asyncio tasks, each with its own DB session/connection,
    # racing the exact same incident+evidence -- the atomicity guarantee
    # must come from conversation_control.alert_claim's own UNIQUE
    # constraint + ON CONFLICT, not from anything in this test.
    control, sessions = real_control_db
    evidence = _evidence(snippet="culpa")

    async def attempt():
        async with sessions() as db:
            decision = await decide_owner_alert(control, db, contact_id=42, instance="dario", evidence=evidence, window_seconds=3600, now=NOW)
            await db.commit()
            return decision.should_alert

    results = await asyncio.gather(*[attempt() for _ in range(15)])
    assert results.count(True) == 1
    assert results.count(False) == 14


@pytest.mark.asyncio
async def test_real_store_different_contacts_are_independent(real_control_db):
    # contact 43 is already seeded by the shared conftest.py fixture.
    control, sessions = real_control_db
    evidence = _evidence(snippet="culpa")
    async with sessions() as db:
        a = await decide_owner_alert(control, db, contact_id=42, instance="dario", evidence=evidence, window_seconds=3600, now=NOW)
        await db.commit()
    async with sessions() as db:
        b = await decide_owner_alert(control, db, contact_id=43, instance="dario", evidence=evidence, window_seconds=3600, now=NOW)
        await db.commit()
    assert a.should_alert is True
    assert b.should_alert is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
