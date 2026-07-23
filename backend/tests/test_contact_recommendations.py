"""Deterministic Recommendation Engine -- Release 1.5, P0-4.

Pure unit tests against `contacts/recommendations.py` directly, no DB
session -- same style `test_contact_intelligence.py` already uses.
Integration coverage (the endpoints actually wiring this in and
executing via the Tool Registry) lives in
`test_contact_recommendations_endpoint.py`.
"""

import dataclasses
from datetime import datetime, timezone

import pytest

from contacts.intelligence import Signal
from contacts.recommendations import build_recommendations
from models.contact import Contact

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _contact() -> Contact:
    return Contact(id=1, name="Ana Souza")


def test_no_signals_produce_no_recommendations():
    assert build_recommendations(_contact(), [], now=NOW) == []


def test_info_severity_signal_alone_produces_no_recommendation():
    """no_interaction_ever is info-severity -- must never be escalated
    into a suggested action, matching P0-3's own choice."""
    signal = Signal(
        code="no_interaction_ever", kind="risk", severity="info", reason="x"
    )
    assert build_recommendations(_contact(), [signal], now=NOW) == []


def test_opportunity_signal_never_produces_a_recommendation():
    signal = Signal(
        code="healthy_and_quiet", kind="opportunity", severity="info", reason="x"
    )
    assert build_recommendations(_contact(), [signal], now=NOW) == []


## --- check_pending_tasks: generated ---------------------------------------------------
def test_check_pending_tasks_generated_by_overdue_commitment():
    signal = Signal(
        code="overdue_commitment",
        kind="risk",
        severity="urgent",
        reason="1 pending task(s) past their due date.",
    )
    recommendations = build_recommendations(_contact(), [signal], now=NOW)
    assert len(recommendations) == 1
    rec = recommendations[0]
    assert rec.type == "check_pending_tasks"
    # priority
    assert rec.priority == "urgent"
    # confidence
    assert rec.confidence == 95
    # explanation
    assert rec.explanation == signal.reason
    # supporting_signals
    assert rec.supporting_signals == ["overdue_commitment"]
    # execution shape -- manual-only, no confirmation flow
    assert rec.confirmation_required is False
    assert rec.execution_target is None
    assert rec.execution_payload is None
    # expiration -- no TTL for a link-only recommendation
    assert rec.expires_at is None


## --- check_pending_tasks: not generated ------------------------------------------------
def test_check_pending_tasks_not_generated_without_overdue_commitment():
    signal = Signal(
        code="relationship_stale", kind="risk", severity="attention", reason="stale"
    )
    recommendations = build_recommendations(_contact(), [signal], now=NOW)
    assert "check_pending_tasks" not in {r.type for r in recommendations}


def test_check_pending_tasks_not_generated_by_done_task_signal_absence():
    """No signal at all (e.g. the overdue task was completed) -- no
    recommendation is fabricated from nothing."""
    assert build_recommendations(_contact(), [], now=NOW) == []


## --- follow_up: generated --------------------------------------------------------------
def test_follow_up_generated_by_no_reply_to_inbound():
    signal = Signal(
        code="no_reply_to_inbound",
        kind="risk",
        severity="attention",
        reason="Last message was inbound 2.0 day(s) ago with no reply since.",
    )
    recommendations = build_recommendations(_contact(), [signal], now=NOW)
    assert len(recommendations) == 1
    rec = recommendations[0]
    assert rec.type == "follow_up"
    # priority
    assert rec.priority == "attention"
    # confidence
    assert rec.confidence == 65
    # explanation
    assert rec.explanation == signal.reason
    # supporting_signals
    assert rec.supporting_signals == ["no_reply_to_inbound"]
    # execution shape -- executable, requires confirmation
    assert rec.confirmation_required is True
    assert rec.execution_target == "create_task"
    assert rec.execution_payload is not None
    assert "Ana Souza" in rec.execution_payload["title"]
    # expiration -- has a TTL (checked precisely below)
    assert rec.expires_at is not None


def test_follow_up_generated_by_relationship_stale():
    signal = Signal(
        code="relationship_stale", kind="risk", severity="attention", reason="stale"
    )
    rec = build_recommendations(_contact(), [signal], now=NOW)[0]
    assert rec.type == "follow_up"
    assert rec.priority == "attention"
    assert rec.confidence == 65
    assert rec.explanation == "stale"
    assert rec.supporting_signals == ["relationship_stale"]


def test_follow_up_generated_by_relationship_at_risk_with_urgent_priority():
    signal = Signal(
        code="relationship_at_risk", kind="risk", severity="urgent", reason="at risk"
    )
    rec = build_recommendations(_contact(), [signal], now=NOW)[0]
    assert rec.type == "follow_up"
    assert rec.priority == "urgent"
    assert rec.confidence == 95
    assert rec.explanation == "at risk"
    assert rec.supporting_signals == ["relationship_at_risk"]


## --- follow_up: not generated -----------------------------------------------------------
def test_follow_up_not_generated_by_overdue_commitment_alone():
    """overdue_commitment drives check_pending_tasks only -- it must not
    also, independently, produce a follow_up."""
    signal = Signal(
        code="overdue_commitment", kind="risk", severity="urgent", reason="overdue"
    )
    recommendations = build_recommendations(_contact(), [signal], now=NOW)
    assert "follow_up" not in {r.type for r in recommendations}


def test_follow_up_not_generated_by_info_or_opportunity_signals():
    signals = [
        Signal(code="no_interaction_ever", kind="risk", severity="info", reason="x"),
        Signal(
            code="upcoming_meeting_prepared",
            kind="opportunity",
            severity="info",
            reason="x",
        ),
    ]
    assert build_recommendations(_contact(), signals, now=NOW) == []


def test_follow_up_tie_break_prefers_at_risk_over_stale_and_no_reply():
    """Only one follow_up recommendation per contact -- when more than
    one qualifying signal fires, the highest-priority one wins, same
    fixed order suggested_next_action already uses."""
    signals = [
        Signal(code="relationship_stale", kind="risk", severity="attention", reason="stale"),
        Signal(code="no_reply_to_inbound", kind="risk", severity="attention", reason="no reply"),
        Signal(code="relationship_at_risk", kind="risk", severity="urgent", reason="at risk"),
    ]
    recommendations = build_recommendations(_contact(), signals, now=NOW)
    follow_ups = [r for r in recommendations if r.type == "follow_up"]
    assert len(follow_ups) == 1
    assert follow_ups[0].supporting_signals == ["relationship_at_risk"]
    assert follow_ups[0].explanation == "at risk"


def test_overdue_and_follow_up_can_both_appear_independently():
    signals = [
        Signal(code="overdue_commitment", kind="risk", severity="urgent", reason="overdue"),
        Signal(code="relationship_stale", kind="risk", severity="attention", reason="stale"),
    ]
    recommendations = build_recommendations(_contact(), signals, now=NOW)
    types = {r.type for r in recommendations}
    assert types == {"check_pending_tasks", "follow_up"}


## --- deterministic output ----------------------------------------------------------------
def test_recommendation_ids_are_deterministic_and_stable():
    signal = Signal(code="overdue_commitment", kind="risk", severity="urgent", reason="x")
    first = build_recommendations(_contact(), [signal], now=NOW)
    second = build_recommendations(_contact(), [signal], now=NOW)
    assert first[0].id == second[0].id == "1-check_pending_tasks"


def test_full_recommendation_equality_across_repeated_calls():
    """Not just the id -- the entire Recommendation object (every field)
    must be identical given identical inputs. `Recommendation` is a
    frozen dataclass, so `==` compares by value, not identity."""
    signals = [
        Signal(code="overdue_commitment", kind="risk", severity="urgent", reason="x"),
        Signal(code="relationship_stale", kind="risk", severity="attention", reason="y"),
    ]
    first = build_recommendations(_contact(), signals, now=NOW)
    second = build_recommendations(_contact(), signals, now=NOW)
    assert first == second


def test_follow_up_expires_at_matches_reply_sla_window():
    from utils.config import get_settings

    settings = get_settings()
    signal = Signal(code="no_reply_to_inbound", kind="risk", severity="attention", reason="x")
    rec = build_recommendations(_contact(), [signal], now=NOW)[0]
    expected_hours = settings.contact_reply_sla_hours
    assert (rec.expires_at - NOW).total_seconds() / 3600 == expected_hours


## --- immutability (value object) -----------------------------------------------------------
def test_recommendation_is_immutable():
    signal = Signal(code="overdue_commitment", kind="risk", severity="urgent", reason="x")
    rec = build_recommendations(_contact(), [signal], now=NOW)[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.priority = "info"  # type: ignore[misc]


## --- purity: no DB/HTTP/Tool Registry dependency ---------------------------------------------
def test_recommendations_module_has_no_infrastructure_dependency():
    """Guards the architectural boundary explicitly: the Recommendation
    Engine must never import a database session, an HTTP framework, or
    the Tool Registry -- it only describes what should happen, never
    invokes anything."""
    import ast
    import inspect

    import contacts.recommendations as module

    source = inspect.getsource(module)
    tree = ast.parse(source)
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)

    forbidden_substrings = ["sqlalchemy", "fastapi", "agents.tools", "httpx"]
    for name in imported_names:
        for forbidden in forbidden_substrings:
            assert forbidden not in name, (
                f"contacts/recommendations.py imports {name!r} -- "
                "the Recommendation Engine must have no infrastructure dependency"
            )
