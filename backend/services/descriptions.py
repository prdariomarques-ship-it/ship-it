"""Shared human-readable descriptions for domain models used in context
surfaces. Two call sites render the same models the same way —
`orchestrator.context.ContextBuilder` (per-message context for the
Cognitive Pipeline) and `observation.builder.ObservationContextBuilder`
(the standing world-state snapshot) — so one changing wording without the
other can never make a Goal/Task/CalendarEvent read differently depending
on which context surface produced it.
"""

from models.calendar import CalendarEvent
from models.contact import Contact
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


def describe_contact_identity(contact: Contact) -> str:
    """Who the agent is talking to, as saved in the address book -- exists
    because agent prompts (see `agents/prompts/darius_twin_manual.md`,
    "Identificação do contato") assume the contact's saved name is *given*
    up front ("vem informado antes da conversa"), not something the model
    has to guess from conversation history or fetch itself via the
    `find_contact` tool. `contact.name` may itself carry a marker the
    Twin's greeting rule keys off directly (e.g. "Cláudio - Igreja", "Irmã
    Erika") -- passed through verbatim, never parsed here, since that
    pattern-matching is the prompt's job, not this function's."""
    parts = [f"nome salvo: {contact.name}"]
    if contact.categories:
        parts.append(f"categorias: {', '.join(contact.categories)}")
    return "; ".join(parts)
