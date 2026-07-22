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

    overdue_tasks = [
        task
        for task in tasks
        if task.status == TaskStatus.PENDING
        and task.due_date is not None
        and _as_aware(task.due_date, now=now) < now
    ]
    if overdue_tasks:
        signals.append(
            Signal(
                code="overdue_commitment",
                kind="risk",
                severity="urgent",
                reason=f"{len(overdue_tasks)} pending task(s) past their due date.",
            )
        )

    if messages:
        last_message = max(
            messages,
            key=lambda m: _as_aware(m.provider_timestamp or m.created_at, now=now),
        )
        last_message_at = _as_aware(
            last_message.provider_timestamp or last_message.created_at, now=now
        )
        hours_since_last_message = (now - last_message_at).total_seconds() / 3600
        if (
            last_message.direction == MessageDirection.INBOUND
            and hours_since_last_message >= settings.contact_reply_sla_hours
        ):
            days_since_last_message = hours_since_last_message / 24
            signals.append(
                Signal(
                    code="no_reply_to_inbound",
                    kind="risk",
                    severity="attention",
                    reason=(
                        f"Last message was inbound {days_since_last_message:.1f} "
                        "day(s) ago with no reply since."
                    ),
                )
            )

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
        last_interaction = _as_aware(contact.last_interaction_at, now=now)
        days_since_interaction = (now - last_interaction).total_seconds() / 86400
        if days_since_interaction >= settings.contact_at_risk_after_days:
            signals.append(
                Signal(
                    code="relationship_at_risk",
                    kind="risk",
                    severity="urgent",
                    reason=(
                        f"No interaction in {days_since_interaction:.0f} day(s) "
                        f"(>= {settings.contact_at_risk_after_days:.0f}-day "
                        "at-risk threshold)."
                    ),
                )
            )
        elif days_since_interaction >= settings.contact_stale_after_days:
            signals.append(
                Signal(
                    code="relationship_stale",
                    kind="risk",
                    severity="attention",
                    reason=(
                        f"No interaction in {days_since_interaction:.0f} day(s) "
                        f"(>= {settings.contact_stale_after_days:.0f}-day "
                        "stale threshold)."
                    ),
                )
            )

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

    if overdue_task_count > 0:
        signals.append(
            Signal(
                code="overdue_commitment",
                kind="risk",
                severity="urgent",
                reason=f"{overdue_task_count} pending task(s) past their due date.",
            )
        )

    if last_message_direction == MessageDirection.INBOUND and last_message_at is not None:
        hours_since_last_message = (
            now - _as_aware(last_message_at, now=now)
        ).total_seconds() / 3600
        if hours_since_last_message >= settings.contact_reply_sla_hours:
            days_since_last_message = hours_since_last_message / 24
            signals.append(
                Signal(
                    code="no_reply_to_inbound",
                    kind="risk",
                    severity="attention",
                    reason=(
                        f"Last message was inbound {days_since_last_message:.1f} "
                        "day(s) ago with no reply since."
                    ),
                )
            )

    if contact.last_interaction_at is not None:
        days_since_interaction = (
            now - _as_aware(contact.last_interaction_at, now=now)
        ).total_seconds() / 86400
        if days_since_interaction >= settings.contact_at_risk_after_days:
            signals.append(
                Signal(
                    code="relationship_at_risk",
                    kind="risk",
                    severity="urgent",
                    reason=(
                        f"No interaction in {days_since_interaction:.0f} day(s) "
                        f"(>= {settings.contact_at_risk_after_days:.0f}-day "
                        "at-risk threshold)."
                    ),
                )
            )
        elif days_since_interaction >= settings.contact_stale_after_days:
            signals.append(
                Signal(
                    code="relationship_stale",
                    kind="risk",
                    severity="attention",
                    reason=(
                        f"No interaction in {days_since_interaction:.0f} day(s) "
                        f"(>= {settings.contact_stale_after_days:.0f}-day "
                        "stale threshold)."
                    ),
                )
            )

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


def suggested_next_action(signals: list[Signal]) -> str:
    """Fixed template picked by the single highest-priority risk signal
    present (`_ACTION_PRIORITY`'s fixed order) -- deterministic, plain text,
    never an executable action (see this module's docstring)."""
    signal_by_code = {signal.code: signal for signal in signals if signal.kind == "risk"}
    for code in _ACTION_PRIORITY:
        if code in signal_by_code:
            return _ACTION_TEMPLATES[code]
    return _NO_ACTION_NEEDED
