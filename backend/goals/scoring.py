"""Deterministic priority scoring for goals.

Kept as a pure function, independent of the DB session, so the ranking logic
is directly unit-testable and explainable on its own -- given a goal, the
score (and therefore the ranking decision) can be reproduced and inspected
without touching the database.
"""
from datetime import datetime, timezone

from models.goal import Goal, GoalPriority

_PRIORITY_WEIGHT: dict[GoalPriority, float] = {
    GoalPriority.URGENT: 100.0,
    GoalPriority.HIGH: 75.0,
    GoalPriority.MEDIUM: 50.0,
    GoalPriority.LOW: 25.0,
}

_MAX_DEADLINE_BONUS = 50.0
_DEADLINE_HORIZON_DAYS = 14.0


def priority_score(goal: Goal, *, now: datetime | None = None) -> float:
    """Higher means more urgent.

    Combines the goal's declared priority with how close its deadline is: a
    goal due within `_DEADLINE_HORIZON_DAYS` gets up to `_MAX_DEADLINE_BONUS`
    extra points, linearly higher the closer (or the more overdue) the
    deadline is. A goal with no deadline gets no bonus at all -- it never
    outranks an equally-prioritized goal that actually has one coming up.
    """
    now = now or datetime.now(timezone.utc)
    score = _PRIORITY_WEIGHT[goal.priority]
    if goal.deadline is None:
        return score
    days_remaining = (goal.deadline - now).total_seconds() / 86400
    urgency = max(0.0, (_DEADLINE_HORIZON_DAYS - days_remaining) / _DEADLINE_HORIZON_DAYS)
    return score + min(urgency, 1.0) * _MAX_DEADLINE_BONUS
