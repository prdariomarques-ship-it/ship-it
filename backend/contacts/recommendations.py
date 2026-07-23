"""Deterministic Recommendation Engine -- Release 1.5, P0-4.

Consumes P0-3's `Signal[]` output only -- never recomputes intelligence,
never decides priority/confidence independently. Every field on every
`Recommendation` traces back to exactly the signal(s) that produced it
(see P0_4_RECOMMENDATIONS_ARCHITECTURE.md's layering: Signals -> Insights
[P0-3, contacts/intelligence.py] -> Recommendations [this module]).

Execution boundary (approved architecture): a `Recommendation` with
`confirmation_required=True` names an existing Tool Registry entry
(`agents/tools/*`) in `execution_target` -- never a new engine. The
Cognitive Planner (`orchestrator/planning.py`) plays no part here: it
exists to interpret ambiguous natural language via an LLM call, and a
Recommendation is never ambiguous by the time it reaches this module.
An LLM, if ever consulted downstream, may only add prose framing to
`explanation` -- it never decides `priority`, `confidence`, or
`execution_target`, and it never executes anything itself.

Only signals with severity in {urgent, attention} become
Recommendations -- an `info`-severity signal (e.g. `no_interaction_ever`)
is deliberately never escalated into a suggested action, matching P0-3's
own choice not to treat "no history yet" as a relationship failure.

v1 scope (deliberately narrow, see P0_4_RECOMMENDATIONS_ARCHITECTURE.md):
two recommendation types, each traced to exactly one signal family, no
fabricated message content or compound conditions not themselves a real
P0-3 signal:
  - FOLLOW_UP: from whichever of no_reply_to_inbound / relationship_stale
    / relationship_at_risk fired (same priority order P0-3's own
    `suggested_next_action` already uses) -- executes via the existing
    `create_task` Tool.
  - CHECK_PENDING_TASKS: from overdue_commitment -- MANUAL_ONLY, no
    execution (which specific task to act on is a human judgment call;
    `current_state.open_tasks` already shows them).
SCHEDULE_MEETING / SEND_WHATSAPP / UPDATE_CONTACT / READ_NOTES /
REVIEW_RELATIONSHIP remain approved for a later iteration, not shipped
here -- deferred to keep this first cut small, fully deterministic, and
fully traceable, not because they are out of scope.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from contacts.intelligence import Signal
from models.contact import Contact
from utils.config import get_settings

RecommendationType = Literal["follow_up", "check_pending_tasks"]

_CONFIDENCE_BY_SEVERITY: dict[str, int] = {"urgent": 95, "attention": 65}

# Same fixed priority order suggested_next_action uses -- one Recommendation
# per contact per family, never a duplicate for the same underlying problem.
_FOLLOW_UP_SIGNAL_PRIORITY: list[str] = [
    "relationship_at_risk",
    "no_reply_to_inbound",
    "relationship_stale",
]

_FOLLOW_UP_TITLE: dict[str, str] = {
    "relationship_at_risk": "Reach out to {name} -- relationship at risk",
    "no_reply_to_inbound": "Reply to {name}",
    "relationship_stale": "Check in with {name}",
}


@dataclass(frozen=True)
class Recommendation:
    id: str
    type: RecommendationType
    priority: str  # "urgent" | "attention" -- Signal.severity verbatim
    confidence: int  # 95 | 65 -- fixed tier, reused from operator.ts verbatim
    explanation: str
    reasoning: list[str]
    supporting_signals: list[str]
    confirmation_required: bool
    execution_target: str | None  # a Tool Registry name, e.g. "create_task"
    execution_payload: dict | None  # draft shown before confirmation
    created_at: datetime
    expires_at: datetime | None


def build_recommendations(
    contact: Contact, signals: list[Signal], *, now: datetime | None = None
) -> list[Recommendation]:
    """Pure, deterministic -- same signals always produce the same
    recommendations. Reads only `signals` (P0-3's own output) and
    `contact.id`/`contact.name` (already loaded, no new query)."""
    now = now or datetime.now(timezone.utc)
    recommendations: list[Recommendation] = []

    risk_by_code = {
        s.code: s for s in signals if s.kind == "risk" and s.severity != "info"
    }

    if "overdue_commitment" in risk_by_code:
        signal = risk_by_code["overdue_commitment"]
        recommendations.append(
            Recommendation(
                id=f"{contact.id}-check_pending_tasks",
                type="check_pending_tasks",
                priority=signal.severity,
                confidence=_CONFIDENCE_BY_SEVERITY[signal.severity],
                explanation=signal.reason,
                reasoning=[signal.reason],
                supporting_signals=["overdue_commitment"],
                confirmation_required=False,
                execution_target=None,
                execution_payload=None,
                created_at=now,
                expires_at=None,
            )
        )

    follow_up_code = next(
        (code for code in _FOLLOW_UP_SIGNAL_PRIORITY if code in risk_by_code), None
    )
    if follow_up_code is not None:
        signal = risk_by_code[follow_up_code]
        settings = get_settings()
        recommendations.append(
            Recommendation(
                id=f"{contact.id}-follow_up",
                type="follow_up",
                priority=signal.severity,
                confidence=_CONFIDENCE_BY_SEVERITY[signal.severity],
                explanation=signal.reason,
                reasoning=[signal.reason],
                supporting_signals=[follow_up_code],
                confirmation_required=True,
                execution_target="create_task",
                execution_payload={
                    "title": _FOLLOW_UP_TITLE[follow_up_code].format(name=contact.name),
                    "priority": "high" if signal.severity == "urgent" else "medium",
                    "due_date": (
                        now + timedelta(hours=settings.contact_reply_sla_hours)
                    ).isoformat(),
                },
                created_at=now,
                expires_at=now + timedelta(hours=settings.contact_reply_sla_hours),
            )
        )

    return recommendations
