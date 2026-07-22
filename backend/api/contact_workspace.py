"""Contact Workspace — Release 1.5, P0-2.

A single aggregate read assembled from data that already exists across
Notes/Tasks/Calendar/Messages/Memory — the same "one endpoint, several
existing queries" shape `dashboard_summary` (api/routes.py) already uses,
not a new storage layer or service. Deliberately not a CRUD page: every
box answers a specific relationship question (who is this, when did we
last talk, what's pending, what have we discussed, what's next) instead
of listing raw rows for their own sake.

Response shape mirrors the requested visual hierarchy directly (one
aggregate read, no frontend orchestration across multiple requests):

    {
      "summary": {...},         # who is this, tags, last interaction --
                                 # relationship_status/suggested_next_action
                                 # are reserved placeholders (null) for P0-3
      "timeline": [...],        # WhatsApp + Notes + Tasks + Meetings, merged
                                 # chronologically (most recent first), each
                                 # entry sharing one stable contract --
                                 # id/type/timestamp/title/subtitle/status/
                                 # source/metadata -- so the frontend never
                                 # branches on which module produced it, and
                                 # a future source slots in unchanged
      "current_state": {...},   # open_tasks, upcoming_events,
                                 # pending_follow_ups, important_notes
      "recommendations": [],    # reserved, empty -- P0-4's job to populate,
                                 # never fabricated here
    }

`Contact` itself has no owner (a single shared WhatsApp address book, by
design — see models/contact.py); Notes/Tasks/Calendar stay owner-scoped
to `current_user.id` exactly as they already are everywhere else in the
app, only additionally filtered to this one contact via the `contact_id`
column added in this same release (Notes already had it, reserved and
unused until now; Tasks/Calendar gained it in this migration).

P0-3's deterministic scoring (relationship health, suggested follow-up,
pending reminders) is deliberately NOT computed here — `relationship_status`
and `suggested_next_action` are typed, present, and `null` so the frontend
has a stable shape to render once that step ships, but nothing here
fabricates a score. `recommendations` stays an empty list for the same
reason: P0-4 is where a recommendation is ever produced, and only ever
behind its own confirmation step.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import CurrentUser
from database.session import get_db
from memory.manager import memory_manager
from models.calendar import CalendarEvent
from models.message import Message, MessageDirection
from models.note import Note
from models.task import Task, TaskStatus
from repositories.base import SQLAlchemyRepository
from repositories.contact import ContactRepository
from repositories.message import MessageRepository
from repositories.note import NoteRepository
from repositories.task import TaskRepository
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/contacts", tags=["contacts"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

_RECENT_MESSAGES_LIMIT = 20
_NOTES_LIMIT = 10
_TASKS_LIMIT = 10
_UPCOMING_EVENTS_LIMIT = 5
_TIMELINE_EVENTS_LIMIT = 10
_FOLLOW_UPS_LIMIT = 5


class _CalendarRepo(SQLAlchemyRepository[CalendarEvent]):
    """No dedicated CalendarEvent repository exists (the internal calendar
    router uses the generic CRUD factory's anonymous repository) — same
    precedent already used for this exact model in
    `agents/tools/productivity.py::_EventRepo` and
    `observation/builder.py::_EmbeddingRepo`, not a new one."""

    model = CalendarEvent


@router.get("/{contact_id}/workspace")
async def get_contact_workspace(
    contact_id: int, db: DbSession, current_user: CurrentUser
) -> dict:
    contact = await ContactRepository(db).get(contact_id)
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found"
        )

    messages = await MessageRepository(db).recent_for_contact(
        contact.id, limit=_RECENT_MESSAGES_LIMIT
    )
    notes = await NoteRepository(db).list(
        user_id=current_user.id, contact_id=contact.id, limit=_NOTES_LIMIT
    )
    open_tasks = await TaskRepository(db).list(
        user_id=current_user.id,
        contact_id=contact.id,
        status=TaskStatus.PENDING,
        limit=_TASKS_LIMIT,
    )
    upcoming_events = await _fetch_upcoming_events(
        db, current_user.id, contact.id, _UPCOMING_EVENTS_LIMIT
    )
    timeline_events = await _fetch_recent_events(
        db, current_user.id, contact.id, _TIMELINE_EVENTS_LIMIT
    )

    preferences: dict = {}
    ai_summary: str | None = None
    try:
        preferences = await memory_manager.get_preferences(db, contact.id)
        ai_summary = await memory_manager.get_summary(db, contact.id)
    except Exception as exc:  # noqa: BLE001 - memory is an enhancement, never a requirement
        logger.warning("Contact workspace memory lookup skipped: %s", exc)

    outbound = [m for m in messages if m.direction == MessageDirection.OUTBOUND]
    important_notes = sorted(notes, key=lambda note: not note.pinned)

    return {
        "summary": {
            "id": contact.id,
            "name": contact.name,
            "phone": contact.phone,
            "categories": contact.categories,
            "tags": contact.tags,
            "last_interaction_at": contact.last_interaction_at,
            # Reserved for P0-3 (deterministic relationship scoring) --
            # deliberately null here, never computed by this endpoint.
            "relationship_status": None,
            "suggested_next_action": None,
            "ai_summary": ai_summary,
            "memory": preferences,
        },
        "timeline": _build_timeline(messages, notes, open_tasks, timeline_events),
        "current_state": {
            "open_tasks": [_task_dict(t) for t in open_tasks],
            "upcoming_events": [_event_dict(e) for e in upcoming_events],
            "pending_follow_ups": [
                _message_dict(m) for m in outbound[-_FOLLOW_UPS_LIMIT:]
            ],
            "important_notes": [_note_dict(n) for n in important_notes],
        },
        # Reserved for P0-4 (AI Recommendations, confirmation-gated) --
        # always empty here; this endpoint never produces a recommendation.
        "recommendations": [],
    }


async def _fetch_upcoming_events(
    db: AsyncSession, user_id: int, contact_id: int, limit: int
) -> list[CalendarEvent]:
    statement = (
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.contact_id == contact_id,
            CalendarEvent.starts_at >= datetime.now(timezone.utc),
        )
        .order_by(CalendarEvent.starts_at.asc())
        .limit(limit)
    )
    return list((await db.execute(statement)).scalars().all())


async def _fetch_recent_events(
    db: AsyncSession, user_id: int, contact_id: int, limit: int
) -> list[CalendarEvent]:
    """Past and future both -- for the Timeline's "Meetings" source (a
    relationship history), distinct from `current_state.upcoming_events`
    (future-only, a different question)."""
    statement = (
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user_id, CalendarEvent.contact_id == contact_id
        )
        .order_by(CalendarEvent.starts_at.desc())
        .limit(limit)
    )
    return list((await db.execute(statement)).scalars().all())


def _message_dict(message: Message) -> dict:
    return {
        "id": message.id,
        "direction": message.direction.value,
        "content": message.content,
        "created_at": message.provider_timestamp or message.created_at,
    }


def _note_dict(note: Note) -> dict:
    return {
        "id": note.id,
        "title": note.title,
        "content": note.content,
        "pinned": note.pinned,
        "created_at": note.created_at,
    }


def _task_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status.value,
        "priority": task.priority.value,
        "due_date": task.due_date,
        "created_at": task.created_at,
    }


def _event_dict(event: CalendarEvent) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "starts_at": event.starts_at,
        "location": event.location,
    }


def _build_timeline(
    messages: list[Message],
    notes: list[Note],
    tasks: list[Task],
    events: list[CalendarEvent],
) -> list[dict]:
    """A single chronological view across every source this contact
    already has data in (WhatsApp, Notes, Tasks, Meetings) — no new
    storage, just a merge-sort of entries already loaded above. Every
    entry shares one stable contract (id/type/timestamp/title/subtitle/
    status/source/metadata) regardless of which module produced it, so a
    future source (Email, Calls, Documents, CRM...) only needs to append
    to this same list — the frontend never branches on where an entry
    came from.

    Most recent first, capped at the configured
    `contact_workspace_timeline_limit` (business value lives in Settings,
    not here). Ties on timestamp are broken by (type, id) — deterministic
    and reproducible across requests, never left to incidental Python/DB
    ordering."""
    entries = [
        *(_message_timeline_entry(m) for m in messages),
        *(_note_timeline_entry(n) for n in notes),
        *(_task_timeline_entry(t) for t in tasks),
        *(_meeting_timeline_entry(e) for e in events),
    ]
    entries.sort(key=lambda entry: (entry["timestamp"], entry["_sort_key"]), reverse=True)
    limit = get_settings().contact_workspace_timeline_limit
    return [{k: v for k, v in entry.items() if k != "_sort_key"} for entry in entries[:limit]]


def _message_timeline_entry(message: Message) -> dict:
    return {
        "id": f"message-{message.id}",
        "type": "message",
        "timestamp": message.provider_timestamp or message.created_at,
        "title": message.content[:140],
        "subtitle": None,
        "status": message.direction.value,
        "source": "whatsapp",
        "metadata": {"direction": message.direction.value},
        "_sort_key": ("message", message.id),
    }


def _note_timeline_entry(note: Note) -> dict:
    return {
        "id": f"note-{note.id}",
        "type": "note",
        "timestamp": note.created_at,
        "title": note.title,
        "subtitle": note.content[:140] if note.content else None,
        "status": "pinned" if note.pinned else None,
        "source": "notes",
        "metadata": {"pinned": note.pinned},
        "_sort_key": ("note", note.id),
    }


def _task_timeline_entry(task: Task) -> dict:
    return {
        "id": f"task-{task.id}",
        "type": "task",
        "timestamp": task.created_at,
        "title": task.title,
        "subtitle": None,
        "status": task.status.value,
        "source": "tasks",
        "metadata": {"priority": task.priority.value, "due_date": task.due_date},
        "_sort_key": ("task", task.id),
    }


def _meeting_timeline_entry(event: CalendarEvent) -> dict:
    return {
        "id": f"meeting-{event.id}",
        "type": "meeting",
        "timestamp": event.starts_at,
        "title": event.title,
        "subtitle": event.location,
        "status": None,
        "source": "calendar",
        "metadata": {"location": event.location},
        "_sort_key": ("meeting", event.id),
    }
