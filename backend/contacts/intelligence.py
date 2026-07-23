"""Deterministic relationship intelligence for one contact -- Release 1.5, P0-3.

Pure functions, no DB session -- same discipline as `goals/scoring.py`:
given a contact and the data `get_contact_workspace` already loaded
(messages, notes, tasks, events), every signal, tier, score and suggested
action is reproducible and independently testable without touching a
database.

Boundary (see CONTACT_INTELLIGENCE_ARCHITECTURE.md, "Architectural
decision", approved 2026-07-22): this module produces *understanding
only* -- signals, a relationship tier, a priority score, a plain-text
suggested next action. It never produces an executable action, a
confirmation flow, or a side effect. Turning a `Signal` into something a
user can click and run is P0-4's job (Action Center reuse), not this
module's -- nothing here imports from the Action Center's domain.

Every threshold and per-signal weight below is a `Settings` field, not a
bare literal -- an explicit, current product decision for this feature
(see the architecture doc), even though the closest existing precedent
(`goals/scoring.py`) uses plain module constants instead.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from models.calendar import CalendarEvent
from models.contact import Contact
from models.message import Message, MessageDirection
from models.note import Note
from models.task import Task, TaskStatus
from utils.config import get_settings

SignalKind = Literal["risk", "opportunity"]
Severity = Literal["urgent", "attention", "info"]
Tier = Literal["healthy", "cooling", "cold", "at_risk"]

_TIER_ORDER: dict[Tier, int] = {"healthy": 0, "cooling": 1, "cold": 2, "at_risk": 3}

# Fixed order used to break ties when more than one risk signal fires --
# same determinism discipline as P0-2's timeline (type, id) tie-break.
_ACTION_PRIORITY: list[str] = [
    "overdue_commitment",
    "relationship_at_risk",
    "no_reply_to_inbound",
    "relationship_stale",
    "no_interaction_ever",
]

_ACTION_TEMPLATES: dict[str, str] = {
    "overdue_commitment": "Complete or reschedule the overdue task(s) for this contact.",
    "relationship_at_risk": "Reach out -- there has been no interaction in a long time.",
    "no_reply_to_inbound": "Reply to the last message -- it's been a while with no response.",
    "relationship_stale": "Consider checking in -- this relationship is going quiet.",
    "no_interaction_ever": "No interaction recorded yet for this contact.",
}

_NO_ACTION_NEEDED = "No action needed right now -- this relationship looks healthy."


@dataclass(frozen=True)
class Signal:
    code: str
    kind: SignalKind
    severity: Severity
    reason: str


def _as_aware(value: datetime, *, now: datetime) -> datetime:
    """SQLite (unlike Postgres) drops tzinfo on `DateTime(timezone=True)`
    columns on read-back -- normalize before subtracting, same fix already
    applied in `goals/scoring.py::priority_score`."""
    if value.tzinfo is None:
        return value.replace(tzinfo=now.tzinfo or timezone.utc)
    return value


def _overdue_commitment_signal(overdue_task_count: int) -> Signal | None:
    """Shared by `compute_signals` (counts a full task list) and
    `compute_risk_signals_from_aggregates` (already has the count) -- one
    rule, one place, so the two call sites can never disagree about what
    an overdue count means."""
    if overdue_task_count <= 0:
        return None
    return Signal(
        code="overdue_commitment",
        kind="risk",
        severity="urgent",
        reason=f"{overdue_task_count} pending task(s) past their due date.",
    )


def _no_reply_to_inbound_signal(
    direction: MessageDirection | None,
    message_at: datetime | None,
    *,
    now: datetime,
    reply_sla_hours: float,
) -> Signal | None:
    """Shared by `compute_signals` (derives direction/timestamp from the
    full message list's most recent entry) and
    `compute_risk_signals_from_aggregates` (already has both)."""
    if direction != MessageDirection.INBOUND or message_at is None:
        return None
    hours_since = (now - _as_aware(message_at, now=now)).total_seconds() / 3600
    if hours_since < reply_sla_hours:
        return None
    days_since = hours_since / 24
    return Signal(
        code="no_reply_to_inbound",
        kind="risk",
        severity="attention",
        reason=(
            f"Last message was inbound {days_since:.1f} day(s) ago with no "
            "reply since."
        ),
    )


def _staleness_signal(
    last_interaction_at: datetime | None,
    *,
    now: datetime,
    stale_after_days: float,
    at_risk_after_days: float,
) -> Signal | None:
    """Shared by `compute_signals` and `compute_risk_signals_from_aggregates`
    -- both read `contact.last_interaction_at` identically; factored out so
    the two can never drift on the stale/at-risk threshold comparison."""
    if last_interaction_at is None:
        return None
    days_since = (now - _as_aware(last_interaction_at, now=now)).total_seconds() / 86400
    if days_since >= at_risk_after_days:
        return Signal(
            code="relationship_at_risk",
            kind="risk",
            severity="urgent",
            reason=(
                f"No interaction in {days_since:.0f} day(s) "
                f"(>= {at_risk_after_days:.0f}-day at-risk threshold)."
            ),
        )
    if days_since >= stale_after_days:
        return Signal(
            code="relationship_stale",
            kind="risk",
            severity="attention",
            reason=(
                f"No interaction in {days_since:.0f} day(s) "
                f"(>= {stale_after_days:.0f}-day stale threshold)."
            ),
        )
    return None


def compute_signals(
    contact: Contact,
    messages: list[Message],
    notes: list[Note],
    tasks: list[Task],
    events: list[CalendarEvent],
    *,
    now: datetime | None = None,
) -> list[Signal]:
    """One entry per fired rule -- never a fabricated fact absent supporting
    data. `notes` is accepted for a stable, source-complete call signature
    (mirrors the four sources `_build_timeline` already takes) even though
    no rule reads it today -- no signal here claims anything about note
    content that isn't literally true."""
    now = now or datetime.now(timezone.utc)
    settings = get_settings()
    signals: list[Signal] = []

    overdue_task_count = len(
        [
            task
            for task in tasks
            if task.status == TaskStatus.PENDING
            and task.due_date is not None
            and _as_aware(task.due_date, now=now) < now
        ]
    )
    overdue_signal = _overdue_commitment_signal(overdue_task_count)
    if overdue_signal is not None:
        signals.append(overdue_signal)

    if messages:
        last_message = max(
            messages,
            key=lambda m: _as_aware(m.provider_timestamp or m.created_at, now=now),
        )
        no_reply_signal = _no_reply_to_inbound_signal(
            last_message.direction,
            last_message.provider_timestamp or last_message.created_at,
            now=now,
            reply_sla_hours=settings.contact_reply_sla_hours,
        )
        if no_reply_signal is not None:
            signals.append(no_reply_signal)

    if contact.last_interaction_at is None:
        signals.append(
            Signal(
                code="no_interaction_ever",
                kind="risk",
                severity="info",
                reason="No recorded interaction with this contact yet.",
            )
        )
    else:
        staleness_signal = _staleness_signal(
            contact.last_interaction_at,
            now=now,
            stale_after_days=settings.contact_stale_after_days,
            at_risk_after_days=settings.contact_at_risk_after_days,
        )
        if staleness_signal is not None:
            signals.append(staleness_signal)

    has_active_risk = any(
        signal.kind == "risk" and signal.severity in ("urgent", "attention")
        for signal in signals
    )

    upcoming_events = [
        event for event in events if _as_aware(event.starts_at, now=now) >= now
    ]
    open_tasks = [task for task in tasks if task.status == TaskStatus.PENDING]
    if upcoming_events and not open_tasks:
        signals.append(
            Signal(
                code="upcoming_meeting_prepared",
                kind="opportunity",
                severity="info",
                reason="An upcoming meeting is scheduled with no open task blocking it.",
            )
        )

    if not has_active_risk and contact.last_interaction_at is not None:
        signals.append(
            Signal(
                code="healthy_and_quiet",
                kind="opportunity",
                severity="info",
                reason="No active risk signal, and the relationship has prior history.",
            )
        )

    return signals


def compute_risk_signals_from_aggregates(
    contact: Contact,
    *,
    overdue_task_count: int,
    last_message_direction: MessageDirection | None,
    last_message_at: datetime | None,
    now: datetime | None = None,
) -> list[Signal]:
    """Same three risk rules as `compute_signals` (overdue commitment,
    unanswered inbound message, relationship staleness), but driven by
    aggregate values instead of full row lists -- the cross-contact
    priority ranking (`GET /contacts/priority`) cannot afford to load every
    contact's full message/task history just to rank them (see
    CONTACT_INTELLIGENCE_ARCHITECTURE.md #13). Intentionally excludes
    opportunity signals and the info-severity data-quality flags
    `compute_signals` also reports -- ranking only cares about what
    contributes to `priority_score`, i.e. risk signals with a non-zero
    weight. Thresholds and weights are the exact same `Settings` fields
    `compute_signals` uses -- a ranked contact and that same contact's
    single-contact workspace never disagree about what fired."""
    now = now or datetime.now(timezone.utc)
    settings = get_settings()
    signals: list[Signal] = []

    overdue_signal = _overdue_commitment_signal(overdue_task_count)
    if overdue_signal is not None:
        signals.append(overdue_signal)

    no_reply_signal = _no_reply_to_inbound_signal(
        last_message_direction,
        last_message_at,
        now=now,
        reply_sla_hours=settings.contact_reply_sla_hours,
    )
    if no_reply_signal is not None:
        signals.append(no_reply_signal)

    if contact.last_interaction_at is not None:
        staleness_signal = _staleness_signal(
            contact.last_interaction_at,
            now=now,
            stale_after_days=settings.contact_stale_after_days,
            at_risk_after_days=settings.contact_at_risk_after_days,
        )
        if staleness_signal is not None:
            signals.append(staleness_signal)

    return signals


def relationship_tier(
    contact: Contact, signals: list[Signal], *, now: datetime | None = None
) -> Tier:
    """Derived primarily from recency, escalated by any active risk signal
    -- the "worse" of the two views, never averaged into a fabricated
    in-between value."""
    now = now or datetime.now(timezone.utc)
    settings = get_settings()

    recency_tier: Tier = "healthy"
    if contact.last_interaction_at is not None:
        days_since_interaction = (
            now - _as_aware(contact.last_interaction_at, now=now)
        ).total_seconds() / 86400
        if days_since_interaction >= settings.contact_at_risk_after_days:
            recency_tier = "at_risk"
        elif days_since_interaction >= settings.contact_stale_after_days:
            recency_tier = "cold"

    if any(
        signal.kind == "risk" and signal.severity == "urgent" for signal in signals
    ):
        signal_tier: Tier = "at_risk"
    elif any(
        signal.kind == "risk" and signal.severity == "attention" for signal in signals
    ):
        signal_tier = "cooling"
    else:
        signal_tier = "healthy"

    return max((recency_tier, signal_tier), key=lambda tier: _TIER_ORDER[tier])


def priority_score(signals: list[Signal]) -> float:
    """Higher means more urgent -- risk signals only. Opportunity signals
    never affect this score: mixing "needs attention because something's
    wrong" with "good moment to deepen the relationship" into one number
    would answer two different questions with a single, less honest value
    (see CONTACT_INTELLIGENCE_ARCHITECTURE.md, Opportunity model)."""
    settings = get_settings()
    weight_by_code = {
        "overdue_commitment": settings.contact_risk_weight_overdue_commitment,
        "no_reply_to_inbound": settings.contact_risk_weight_no_reply_to_inbound,
        "relationship_stale": settings.contact_risk_weight_relationship_stale,
        "relationship_at_risk": settings.contact_risk_weight_relationship_at_risk,
    }
    return sum(
        weight_by_code.get(signal.code, 0.0)
        for signal in signals
        if signal.kind == "risk"
    )


def _highest_priority_signal(signals: list[Signal], *, exclude_info: bool) -> Signal | None:
    """Shared lookup, fixed order (`_ACTION_PRIORITY`), for both
    `primary_risk_signal` and `suggested_next_action` -- one source of
    truth for "which signal matters most" so the two can never silently
    disagree on ordering. `exclude_info` is the one place they diverge:
    `no_interaction_ever` (severity="info", a data-quality flag -- see
    `priority_score`'s zero weight for it) still deserves an honest
    `suggested_next_action` template, but must never be surfaced as a
    "primary reason" of relationship risk (see `primary_risk_signal`)."""
    signal_by_code = {
        signal.code: signal
        for signal in signals
        if signal.kind == "risk" and not (exclude_info and signal.severity == "info")
    }
    for code in _ACTION_PRIORITY:
        if code in signal_by_code:
            return signal_by_code[code]
    return None


def primary_risk_signal(signals: list[Signal]) -> Signal | None:
    """The single highest-priority *real* risk signal present (severity
    "urgent"/"attention" only) -- the one place that decides "which signal
    is the primary reason" for any caller that needs it (e.g.
    `GET /contacts/priority`'s `primary_reason`). Added in Release 1.5
    hardening: a frontend panel had re-implemented its own severity-only
    ordering to pick a "primary reason" for display, which could silently
    disagree with this function's code-based ordering on a tie between two
    equal-severity signals (e.g. `overdue_commitment` vs
    `relationship_at_risk`, both "urgent") -- the frontend must only
    render this, never re-derive it. Deliberately excludes info-severity
    risk signals (`no_interaction_ever`) -- "no history yet" is not a
    relationship-risk reason (see `test_info_severity_risk_signal_
    contributes_zero_to_score`)."""
    return _highest_priority_signal(signals, exclude_info=True)


def suggested_next_action(signals: list[Signal]) -> str:
    """Fixed template picked by the single highest-priority risk signal
    present -- deterministic, plain text, never an executable action (see
    this module's docstring). Unlike `primary_risk_signal`, info-severity
    signals are eligible here: "no interaction recorded yet" is still an
    honest, useful suggestion even though it isn't a "risk reason"."""
    signal = _highest_priority_signal(signals, exclude_info=False)
    if signal is None:
        return _NO_ACTION_NEEDED
    return _ACTION_TEMPLATES[signal.code]
