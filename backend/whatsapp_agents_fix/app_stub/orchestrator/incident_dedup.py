"""Owner-alert deduplication for the digital twin's risk gate.

2026-10-08, second revision -- the first version of this module (shipped
earlier the same day) defined its own `IncidentStore` Protocol and shipped
a `_InMemoryIncidentStore` "tests only" reference implementation, with the
real Postgres-backed store left as an explicit `NotImplementedError` in
jobs/handlers.py. The review correctly rejected that: a second,
not-yet-built persistence/concurrency system, parallel to whatever the
V2 candidate package already had.

services/conversation_control.py (copied verbatim from the V2 candidate
into this delivery -- see DELIVERY_NOTES.md for its SHA-256 and where it
came from) already implements exactly the atomic, transactional,
concurrency-safe claim primitive this needs: `alert_claim` /
`claim_alert` / `finish_alert`, built on a real Postgres/SQLite table
with a UNIQUE constraint on (contact_id, instance, dedup_key) and
`INSERT ... ON CONFLICT DO NOTHING` -- no read-then-write race, no
in-memory dict, no second schema. Its own test suites (26 offline guard
tests, 1 real-PostgreSQL concurrency test run against a real local
PostgreSQL 16 server, 38 real-SQLite transaction/concurrency tests) all
pass -- see DELIVERY_NOTES.md for the exact commands and results.

This module's ONLY remaining job, per the review's instruction to reuse
rather than duplicate, is answering one pure, storage-free question:
"what dedup_key should today's evidence claim?" -- so that:

  - the SAME evidence recurring under an open incident reuses the SAME
    key, and conversation_control.alert_claim's own uniqueness is what
    suppresses the repeat (no second table needed to know "is this
    still open");
  - a message with a brand NEW id carrying the SAME evidence still
    produces the SAME key (no message_id in the key at all) -- a new id
    must not look like a new incident;
  - evidence that is a mere PARAPHRASE of what already alerted (crying
    today, crying again tomorrow in different words -- see
    twin_risk_gate.group_for_snippet) also produces the SAME key;
  - evidence that is GENUINELY different (a more severe or unrelated
    term under the same contact+instance+category) produces a
    DIFFERENT key, so it can still escalate even while the episode is
    technically still open -- this is not a bare cooldown timer, which
    has no notion of "did the content actually change";
  - after `window_seconds` with no genuinely new evidence, the key
    rolls over to a new bucket, so a real, persistent incident is never
    suppressed forever just because nothing "new" was said in the
    meantime (the review's explicit "evite... suprimir incidentes
    futuros para sempre").

What this module deliberately does NOT do: decide whether a send is
allowed at all (that's conversation_control.allowed/claim_send, driven
by human-pause state -- a separate concern), or track delivery outcome
of the alert itself (that's conversation_control.claim_alert/
finish_alert/close_unknown, called directly by the caller with the key
this module returns).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from orchestrator.twin_risk_gate import RiskEvidence, group_for_snippet


def evidence_group(evidence: RiskEvidence) -> str:
    """Paraphrase-insensitive grouping for THIS evidence. "crise" uses
    twin_risk_gate's explicit term-paraphrase groups (crying, suicidal
    ideation, ...); every other category (negocio, loop, llm_unavailable,
    ...) has only one real concept per category today, so the category
    name itself is the group -- still correct if/when those categories
    grow their own paraphrase sets later, since this is additive."""
    if evidence.category == "crise":
        return group_for_snippet(evidence.snippet)
    return evidence.category


def dedup_key(
    *,
    contact_id: int,
    instance: str,
    category: str,
    group: str,
    now: datetime,
    window_seconds: int,
) -> str:
    """Deterministic, lookup-free. No message_id (a new id carrying the
    same group must produce the same key); includes a coarse time bucket
    so a persistent incident is not suppressed forever once genuinely
    nothing changes. conversation_control.alert_claim's own UNIQUE
    constraint on (contact_id, instance, dedup_key) is the only thing
    that actually decides "is this a fresh claim" -- this function only
    computes which key to ask it about."""
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    bucket = int(now.timestamp() // window_seconds)
    raw = f"{contact_id}:{instance}:{category}:{group}:{bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AlertDecision:
    """What the caller needs to both decide (alert or not) and later
    resolve the outcome through conversation_control (claim_alert /
    finish_alert / close_unknown, using `key`)."""

    should_alert: bool
    key: str
    group: str


async def decide_owner_alert(
    conversation_control,
    db,
    *,
    contact_id: int,
    instance: str,
    evidence: RiskEvidence,
    window_seconds: int,
    now: datetime | None = None,
) -> AlertDecision:
    """Call once per risky `twin_autopilot_check` run. `conversation_control`
    is passed in (not imported at module level) so tests can supply either
    the real module or a lightweight fake with the same `alert_claim`
    signature -- see test_incident_dedup.py for both.

    Returns should_alert=True only when conversation_control.alert_claim
    actually reserved this key for the first time (atomic, inside the
    database -- not a read-then-write check here). The caller must still
    call conversation_control.claim_alert(db, contact_id, instance, key)
    before actually sending, and finish_alert/close_unknown afterwards --
    this function only decides whether today's evidence is worth
    attempting at all.
    """
    group = evidence_group(evidence)
    key = dedup_key(
        contact_id=contact_id,
        instance=instance,
        category=evidence.category,
        group=group,
        now=now or datetime.now(timezone.utc),
        window_seconds=window_seconds,
    )
    reserved = await conversation_control.alert_claim(db, contact_id, instance, key)
    return AlertDecision(should_alert=reserved, key=key, group=group)
