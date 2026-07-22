"""Deterministic relationship intelligence -- Release 1.5, P0-3.

Pure unit tests against `contacts/intelligence.py` directly, no DB session
-- same style `tests/test_goals.py` already uses for `goals/scoring.py`:
construct model objects in memory, call the pure function, assert on the
result. Integration coverage (the endpoint actually wiring this in) lives
in `test_contact_workspace.py` (single-contact) and
`test_contact_priority.py` (cross-contact ranking).
"""

from datetime import datetime, timedelta, timezone

from contacts.intelligence import (
    Signal,
    compute_risk_signals_from_aggregates,
    compute_signals,
    priority_score,
    relationship_tier,
    suggested_next_action,
)
from models.calendar import CalendarEvent
from models.contact import Contact
from models.message import Message, MessageDirection
from models.task import Task, TaskPriority, TaskStatus
from utils.config import get_settings

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _contact(*, last_interaction_at: datetime | None) -> Contact:
    return Contact(name="Contato de teste", last_interaction_at=last_interaction_at)


def _message(*, direction: MessageDirection, at: datetime) -> Message:
    return Message(direction=direction, content="oi", created_at=at, provider_timestamp=at)


def _pending_task(*, due_date: datetime | None) -> Task:
    return Task(
        title="Tarefa",
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        due_date=due_date,
        created_at=NOW,
    )


def _event(*, starts_at: datetime) -> CalendarEvent:
    return CalendarEvent(title="Reunião", starts_at=starts_at)


# --- compute_signals: overdue commitment -----------------------------------------------
def test_overdue_task_fires_urgent_risk_signal():
    contact = _contact(last_interaction_at=NOW)
    overdue = _pending_task(due_date=NOW - timedelta(days=1))
    signals = compute_signals(contact, [], [], [overdue], [], now=NOW)
    codes = {s.code: s for s in signals}
    assert codes["overdue_commitment"].kind == "risk"
    assert codes["overdue_commitment"].severity == "urgent"


def test_task_due_in_the_future_does_not_fire_overdue_signal():
    contact = _contact(last_interaction_at=NOW)
    future_task = _pending_task(due_date=NOW + timedelta(days=1))
    signals = compute_signals(contact, [], [], [future_task], [], now=NOW)
    assert "overdue_commitment" not in {s.code for s in signals}


def test_pending_task_with_no_due_date_does_not_fire_overdue_signal():
    """A task with no due_date at all is not "overdue" -- that word only
    means anything relative to a date that exists."""
    contact = _contact(last_interaction_at=NOW)
    no_due_date_task = _pending_task(due_date=None)
    signals = compute_signals(contact, [], [], [no_due_date_task], [], now=NOW)
    assert "overdue_commitment" not in {s.code for s in signals}


def test_done_task_past_due_date_does_not_fire_overdue_signal():
    contact = _contact(last_interaction_at=NOW)
    done_task = Task(
        title="Feita",
        status=TaskStatus.DONE,
        priority=TaskPriority.MEDIUM,
        due_date=NOW - timedelta(days=5),
        created_at=NOW,
    )
    signals = compute_signals(contact, [], [], [done_task], [], now=NOW)
    assert "overdue_commitment" not in {s.code for s in signals}


# --- compute_signals: unanswered inbound message ---------------------------------------
def test_unanswered_inbound_message_past_sla_fires_attention_signal():
    contact = _contact(last_interaction_at=NOW)
    inbound = _message(direction=MessageDirection.INBOUND, at=NOW - timedelta(hours=48))
    signals = compute_signals(contact, [inbound], [], [], [], now=NOW)
    codes = {s.code: s for s in signals}
    assert codes["no_reply_to_inbound"].severity == "attention"


def test_recent_inbound_message_within_sla_does_not_fire():
    contact = _contact(last_interaction_at=NOW)
    inbound = _message(direction=MessageDirection.INBOUND, at=NOW - timedelta(hours=1))
    signals = compute_signals(contact, [inbound], [], [], [], now=NOW)
    assert "no_reply_to_inbound" not in {s.code for s in signals}


def test_outbound_last_message_never_fires_no_reply_signal():
    contact = _contact(last_interaction_at=NOW)
    outbound = _message(direction=MessageDirection.OUTBOUND, at=NOW - timedelta(days=10))
    signals = compute_signals(contact, [outbound], [], [], [], now=NOW)
    assert "no_reply_to_inbound" not in {s.code for s in signals}


def test_only_the_truly_most_recent_message_is_considered():
    """Regression guard for the `max()` selection in compute_signals:
    passing an inbound message first and a more recent outbound message
    second must not accidentally read the first (list-order) message as
    "most recent" -- it must genuinely pick the latest timestamp."""
    contact = _contact(last_interaction_at=NOW)
    older_inbound = _message(
        direction=MessageDirection.INBOUND, at=NOW - timedelta(hours=48)
    )
    newer_outbound = _message(
        direction=MessageDirection.OUTBOUND, at=NOW - timedelta(hours=1)
    )
    signals = compute_signals(
        contact, [older_inbound, newer_outbound], [], [], [], now=NOW
    )
    assert "no_reply_to_inbound" not in {s.code for s in signals}


# --- compute_signals: relationship staleness -------------------------------------------
def test_no_interaction_ever_fires_info_signal_not_urgent():
    contact = _contact(last_interaction_at=None)
    signals = compute_signals(contact, [], [], [], [], now=NOW)
    codes = {s.code: s for s in signals}
    assert codes["no_interaction_ever"].severity == "info"
    assert "relationship_at_risk" not in codes
    assert "relationship_stale" not in codes


def test_stale_threshold_boundary_is_exact():
    settings_stale_days = 14  # default -- see utils/config.py
    just_under = _contact(
        last_interaction_at=NOW - timedelta(days=settings_stale_days - 1)
    )
    at_threshold = _contact(
        last_interaction_at=NOW - timedelta(days=settings_stale_days)
    )
    assert "relationship_stale" not in {
        s.code for s in compute_signals(just_under, [], [], [], [], now=NOW)
    }
    assert "relationship_stale" in {
        s.code for s in compute_signals(at_threshold, [], [], [], [], now=NOW)
    }


def test_very_stale_escalates_to_at_risk_not_stale():
    contact = _contact(last_interaction_at=NOW - timedelta(days=90))
    signals = compute_signals(contact, [], [], [], [], now=NOW)
    codes = {s.code for s in signals}
    assert "relationship_at_risk" in codes
    assert "relationship_stale" not in codes  # mutually exclusive, not both


# --- compute_signals: opportunities -----------------------------------------------------
def test_upcoming_meeting_with_no_open_task_is_an_opportunity():
    contact = _contact(last_interaction_at=NOW)
    upcoming = _event(starts_at=NOW + timedelta(days=1))
    signals = compute_signals(contact, [], [], [], [upcoming], now=NOW)
    codes = {s.code: s for s in signals}
    assert codes["upcoming_meeting_prepared"].kind == "opportunity"


def test_upcoming_meeting_with_an_open_task_is_not_reported_as_prepared():
    """An upcoming meeting with something still open blocking it is not the
    same "nothing left to do" opportunity -- must not fire."""
    contact = _contact(last_interaction_at=NOW)
    upcoming = _event(starts_at=NOW + timedelta(days=1))
    open_task = _pending_task(due_date=NOW + timedelta(days=2))
    signals = compute_signals(contact, [], [], [open_task], [upcoming], now=NOW)
    assert "upcoming_meeting_prepared" not in {s.code for s in signals}


def test_healthy_and_quiet_when_nothing_fires():
    contact = _contact(last_interaction_at=NOW - timedelta(days=1))
    signals = compute_signals(contact, [], [], [], [], now=NOW)
    codes = {s.code: s for s in signals}
    assert codes["healthy_and_quiet"].kind == "opportunity"


def test_healthy_and_quiet_absent_when_a_risk_signal_fires():
    contact = _contact(last_interaction_at=NOW)
    overdue = _pending_task(due_date=NOW - timedelta(days=1))
    signals = compute_signals(contact, [], [], [overdue], [], now=NOW)
    assert "healthy_and_quiet" not in {s.code for s in signals}


def test_empty_contact_produces_no_crash_and_a_sane_result():
    """The empty-relationship case: no messages, notes, tasks, or events at
    all. Must not crash, must not fabricate a risk signal from nothing."""
    contact = _contact(last_interaction_at=None)
    signals = compute_signals(contact, [], [], [], [], now=NOW)
    assert {s.code for s in signals} == {"no_interaction_ever"}


# --- relationship_tier -------------------------------------------------------------------
def test_tier_healthy_when_recent_and_no_signal():
    contact = _contact(last_interaction_at=NOW - timedelta(days=1))
    signals = compute_signals(contact, [], [], [], [], now=NOW)
    assert relationship_tier(contact, signals, now=NOW) == "healthy"


def test_tier_cooling_when_recent_but_a_signal_fires():
    contact = _contact(last_interaction_at=NOW - timedelta(hours=1))
    inbound = _message(direction=MessageDirection.INBOUND, at=NOW - timedelta(hours=48))
    signals = compute_signals(contact, [inbound], [], [], [], now=NOW)
    assert relationship_tier(contact, signals, now=NOW) == "cooling"


def test_tier_cold_when_stale_and_no_urgent_signal():
    contact = _contact(last_interaction_at=NOW - timedelta(days=20))
    signals = compute_signals(contact, [], [], [], [], now=NOW)
    assert relationship_tier(contact, signals, now=NOW) == "cold"


def test_tier_at_risk_when_very_stale():
    contact = _contact(last_interaction_at=NOW - timedelta(days=90))
    signals = compute_signals(contact, [], [], [], [], now=NOW)
    assert relationship_tier(contact, signals, now=NOW) == "at_risk"


def test_tier_at_risk_when_urgent_signal_fires_even_if_recent():
    contact = _contact(last_interaction_at=NOW)
    overdue = _pending_task(due_date=NOW - timedelta(days=1))
    signals = compute_signals(contact, [], [], [overdue], [], now=NOW)
    assert relationship_tier(contact, signals, now=NOW) == "at_risk"


def test_no_interaction_ever_is_not_at_risk():
    """A brand-new contact with no history yet is a data-quality flag
    (info), not a relationship failure -- must not read as 'at_risk'."""
    contact = _contact(last_interaction_at=None)
    signals = compute_signals(contact, [], [], [], [], now=NOW)
    assert relationship_tier(contact, signals, now=NOW) == "healthy"


# --- priority_score -----------------------------------------------------------------------
def test_more_risk_signals_score_higher():
    healthy = _contact(last_interaction_at=NOW)
    at_risk = _contact(last_interaction_at=NOW - timedelta(days=90))
    healthy_signals = compute_signals(healthy, [], [], [], [], now=NOW)
    at_risk_signals = compute_signals(at_risk, [], [], [], [], now=NOW)
    assert priority_score(at_risk_signals) > priority_score(healthy_signals)


def test_opportunity_signals_never_affect_priority_score():
    contact = _contact(last_interaction_at=NOW - timedelta(days=1))
    upcoming = _event(starts_at=NOW + timedelta(days=1))
    signals = compute_signals(contact, [], [], [], [upcoming], now=NOW)
    assert priority_score(signals) == 0.0


def test_each_weighted_risk_signal_contributes_exactly_its_configured_weight():
    """Isolates each of the 4 weighted signal codes -- not just "more
    signals score higher" in aggregate, but the exact configured weight
    per code (see utils/config.py)."""
    settings = get_settings()
    weight_by_code = {
        "overdue_commitment": settings.contact_risk_weight_overdue_commitment,
        "no_reply_to_inbound": settings.contact_risk_weight_no_reply_to_inbound,
        "relationship_stale": settings.contact_risk_weight_relationship_stale,
        "relationship_at_risk": settings.contact_risk_weight_relationship_at_risk,
    }
    for code, weight in weight_by_code.items():
        signal = Signal(code=code, kind="risk", severity="attention", reason="x")
        assert priority_score([signal]) == weight


def test_info_severity_risk_signal_contributes_zero_to_score():
    """`no_interaction_ever` is kind="risk" but carries no configured
    weight -- it's a data-quality flag, not something that should inflate
    priority ranking."""
    signal = Signal(code="no_interaction_ever", kind="risk", severity="info", reason="x")
    assert priority_score([signal]) == 0.0


# --- suggested_next_action: deterministic tie-break ----------------------------------------
def test_suggested_action_picks_highest_priority_signal_deterministically():
    contact = _contact(last_interaction_at=NOW - timedelta(days=90))
    overdue = _pending_task(due_date=NOW - timedelta(days=1))
    signals = compute_signals(contact, [], [], [overdue], [], now=NOW)
    codes = {s.code for s in signals}
    assert {"overdue_commitment", "relationship_at_risk"} <= codes
    action_1 = suggested_next_action(signals)
    action_2 = suggested_next_action(list(reversed(signals)))
    assert action_1 == action_2  # order-independent, same tie-break every time
    assert "overdue" in action_1.lower()  # overdue_commitment outranks relationship_at_risk


def test_suggested_action_is_honest_when_nothing_fires():
    contact = _contact(last_interaction_at=NOW - timedelta(days=1))
    signals = compute_signals(contact, [], [], [], [], now=NOW)
    assert suggested_next_action(signals) == "No action needed right now -- this relationship looks healthy."


def test_suggested_action_for_no_reply_to_inbound_alone():
    contact = _contact(last_interaction_at=NOW)
    inbound = _message(direction=MessageDirection.INBOUND, at=NOW - timedelta(hours=48))
    signals = compute_signals(contact, [inbound], [], [], [], now=NOW)
    assert suggested_next_action(signals) == (
        "Reply to the last message -- it's been a while with no response."
    )


def test_suggested_action_for_relationship_stale_alone():
    contact = _contact(last_interaction_at=NOW - timedelta(days=20))
    signals = compute_signals(contact, [], [], [], [], now=NOW)
    assert suggested_next_action(signals) == (
        "Consider checking in -- this relationship is going quiet."
    )


# --- compute_risk_signals_from_aggregates: must agree with compute_signals -----------------
def test_aggregate_path_agrees_with_full_row_path_for_overdue_and_staleness():
    """The bulk-ranking aggregate path and the single-contact detail path
    share the same Settings thresholds -- a contact must never be scored
    differently depending on which endpoint asked."""
    contact = _contact(last_interaction_at=NOW - timedelta(days=90))
    overdue = _pending_task(due_date=NOW - timedelta(days=1))

    full_signals = compute_signals(contact, [], [], [overdue], [], now=NOW)
    aggregate_signals = compute_risk_signals_from_aggregates(
        contact,
        overdue_task_count=1,
        last_message_direction=None,
        last_message_at=None,
        now=NOW,
    )

    assert priority_score(full_signals) == priority_score(aggregate_signals)
    assert relationship_tier(contact, full_signals, now=NOW) == relationship_tier(
        contact, aggregate_signals, now=NOW
    )


def test_aggregate_path_with_no_signals_is_empty():
    contact = _contact(last_interaction_at=NOW)
    signals = compute_risk_signals_from_aggregates(
        contact,
        overdue_task_count=0,
        last_message_direction=None,
        last_message_at=None,
        now=NOW,
    )
    assert signals == []
