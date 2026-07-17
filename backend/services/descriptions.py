"""Shared human-readable descriptions for domain models used in context
surfaces. Two call sites render the same models the same way —
`orchestrator.context.ContextBuilder` (per-message context for the
Cognitive Pipeline) and `observation.builder.ObservationContextBuilder`
(the standing world-state snapshot) — so one changing wording without the
other can never make a Goal/Task/CalendarEvent read differently depending
on which context surface produced it.
"""

from models.calendar import CalendarEvent
from models.goal import Goal
from models.task import Task


def describe_goal(goal: Goal) -> str:
    parts = [goal.title, f"prioridade {goal.priority.value}"]
    if goal.deadline:
        parts.append(f"prazo {goal.deadline.date().isoformat()}")
    if goal.progress_percent:
        parts.append(f"{goal.progress_percent}% concluída")
    return "; ".join(parts)


def describe_task(task: Task) -> str:
    parts = [task.title]
    if task.due_date:
        parts.append(f"prazo {task.due_date.date().isoformat()}")
    return "; ".join(parts)


def describe_calendar_event(event: CalendarEvent) -> str:
    when = event.starts_at.isoformat()
    return f"{event.title} em {when}" + (
        f" ({event.location})" if event.location else ""
    )
