"""Contact Workspace — Release 1.5, P0-2 + P0-3 (Contact Intelligence) + P0-4 (Recommendations).

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
                                 # computed deterministically (P0-3, see
                                 # contacts/intelligence.py) from data this
                                 # endpoint already loads -- no new query
      "timeline": [...],        # WhatsApp + Notes + Tasks + Meetings, merged
                                 # chronologically (most recent first), each
                                 # entry sharing one stable contract --
                                 # id/type/timestamp/title/subtitle/status/
                                 # source/metadata -- so the frontend never
                                 # branches on which module produced it, and
                                 # a future source slots in unchanged
      "current_state": {...},   # open_tasks, upcoming_events,
                                 # pending_follow_ups, important_notes
      "recommendations": [...], # deterministic, built from the same
                                 # signals above (P0-4, see
                                 # contacts/recommendations.py) -- never
                                 # independently computed or LLM-decided
    }

`Contact` itself has no owner (a single shared WhatsApp address book, by
design — see models/contact.py); Notes/Tasks/Calendar stay owner-scoped
to `current_user.id` exactly as they already are everywhere else in the
app, only additionally filtered to this one contact via the `contact_id`
column added in this same release (Notes already had it, reserved and
unused until now; Tasks/Calendar gained it in this migration).

P0-3's deterministic scoring (`contacts/intelligence.py`) fills
`relationship_status`/`suggested_next_action` from data already loaded
above -- understanding only, per CONTACT_INTELLIGENCE_ARCHITECTURE.md's
"Architectural decision": no executable action, no side effect, no
confirmation flow.

P0-4's Recommendation Engine (`contacts/recommendations.py`) consumes
that same signal list -- never recomputes intelligence, never decides
priority/confidence independently. A recommendation with
`confirmation_required=True` names an existing Tool Registry entry in
`execution_target`; nothing executes until `POST .../recommendations/
{recommendation_id}/execute` is called, which re-derives the
recommendation from live data before dispatching (see that endpoint's
own docstring below) -- this GET never performs a write.
"""

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import agents.tools.productivity  # noqa: F401 -- side effect: registers
# "create_task" (and its sibling tools) in the Tool Registry. Registration
# normally happens as a side effect of agent module discovery, which is
# itself lazy (agents.registry._discover(), triggered by get_agent()) --
# this endpoint deliberately never runs an agent or calls get_agent()
# (no Cognitive Planner, no LLM, per the approved P0-4 architecture), so
# without this explicit import "create_task" would simply never be
# registered by the time execute_contact_recommendation looks it up.
from agents.tools.base import ToolContext
from agents.tools.registry import get_tool
from auth.dependencies import CurrentUser
from database.session import get_db
from memory.manager import memory_manager
from models.calendar import CalendarEvent
from models.contact import Contact
from models.message import Message, MessageDirection
from models.note import Note
from models.task import Task, TaskStatus
from repositories.contact import ContactRepository
from repositories.message import MessageRepository
from repositories.note import NoteRepository
from repositories.task import TaskRepository
from contacts.intelligence import (
    Signal,
    compute_risk_signals_from_aggregates,
    compute_signals,
    primary_risk_signal,
    priority_score,
    relationship_tier,
    suggested_next_action,
)
from contacts.recommendations import Recommendation, build_recommendations
from services.audit import record_log
from utils import messages as user_messages
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


@router.get("/{contact_id}/workspace")
async def get_contact_workspace(
    contact_id: int, db: DbSession, current_user: CurrentUser
) -> dict:
    contact = await ContactRepository(db).get(contact_id)
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=user_messages.CONTACT_NOT_FOUND,
        )

    messages, notes, open_tasks, upcoming_events = await _load_signal_inputs(
        db, current_user.id, contact.id
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

    signals = compute_signals(contact, messages, notes, open_tasks, upcoming_events)

    return {
        "summary": {
            "id": contact.id,
            "name": contact.name,
            "phone": contact.phone,
            "categories": contact.categories,
            "tags": contact.tags,
            "last_interaction_at": contact.last_interaction_at,
            # Computed in-memory from data already loaded above -- P0-3
            # (Contact Intelligence). Understanding only: no executable
            # action, no side effect. See contacts/intelligence.py and
            # CONTACT_INTELLIGENCE_ARCHITECTURE.md.
            "relationship_status": _relationship_status_dict(contact, signals),
            "suggested_next_action": suggested_next_action(signals),
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
        # Deterministic, built from the same `signals` above -- P0-4.
        # Never independently computed; execution (if any) only ever
        # happens via POST .../recommendations/{id}/execute, never here.
        "recommendations": [
            _recommendation_dict(r) for r in build_recommendations(contact, signals)
        ],
    }


@router.post("/{contact_id}/recommendations/{recommendation_id}/execute")
async def execute_contact_recommendation(
    contact_id: int, recommendation_id: str, db: DbSession, current_user: CurrentUser
) -> dict:
    """Confirms and executes one recommendation -- the only write path in
    this module. Never trusts a client-echoed payload: re-derives the
    recommendation from live data first (staleness guard -- see
    CONTACT_INTELLIGENCE_ARCHITECTURE.md and
    P0_4_RECOMMENDATIONS_ARCHITECTURE.md §3/§13), then dispatches to the
    Tool Registry (never the Cognitive Planner -- see
    contacts/recommendations.py's own docstring for why), then records
    the outcome through the same audit path every other admin action
    already uses."""
    contact = await ContactRepository(db).get(contact_id)
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=user_messages.CONTACT_NOT_FOUND,
        )

    signals = await _recompute_signals(db, current_user.id, contact)
    recommendations = build_recommendations(contact, signals)
    recommendation = next(
        (r for r in recommendations if r.id == recommendation_id), None
    )
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=user_messages.RECOMMENDATION_EXPIRED,
        )
    if not recommendation.confirmation_required or recommendation.execution_target is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=user_messages.RECOMMENDATION_NOT_EXECUTABLE,
        )

    tool = get_tool(recommendation.execution_target)
    if tool is None:
        logger.error(
            "Tool %r referenced by recommendation %r is not registered",
            recommendation.execution_target,
            recommendation.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=user_messages.tool_not_registered(recommendation.execution_target),
        )

    tool_context = ToolContext(db=db, user=current_user, contact_id=contact.id)
    raw_result = await tool.run(tool_context, recommendation.execution_payload or {})
    result = json.loads(raw_result)
    ok = "error" not in result

    await record_log(
        db,
        source=f"contacts:recommendation.{recommendation.type}",
        message=f"Recomendação executada: {recommendation.explanation}",
        level="info" if ok else "warning",
        payload={
            "recommendation_id": recommendation.id,
            "contact_id": contact.id,
            "supporting_signals": recommendation.supporting_signals,
            "execution_target": recommendation.execution_target,
            "result": result,
        },
    )

    return {"ok": ok, "result": result}


async def _load_signal_inputs(
    db: AsyncSession, user_id: int, contact_id: int
) -> tuple[list[Message], list[Note], list[Task], list[CalendarEvent]]:
    """The four inputs `compute_signals` needs -- shared by
    `get_contact_workspace` and `_recompute_signals` so the two can never
    drift on what a signal computation is actually based on."""
    messages = await MessageRepository(db).recent_for_contact(
        contact_id, limit=_RECENT_MESSAGES_LIMIT
    )
    notes = await NoteRepository(db).list(
        user_id=user_id, contact_id=contact_id, limit=_NOTES_LIMIT
    )
    open_tasks = await TaskRepository(db).list(
        user_id=user_id,
        contact_id=contact_id,
        status=TaskStatus.PENDING,
        limit=_TASKS_LIMIT,
    )
    upcoming_events = await _fetch_upcoming_events(
        db, user_id, contact_id, _UPCOMING_EVENTS_LIMIT
    )
    return messages, notes, open_tasks, upcoming_events


async def _recompute_signals(
    db: AsyncSession, user_id: int, contact: Contact
) -> list[Signal]:
    """Re-derives the exact same signals `get_contact_workspace` would show
    right now -- the execute endpoint's staleness guard (see
    `execute_contact_recommendation`)."""
    messages, notes, open_tasks, upcoming_events = await _load_signal_inputs(
        db, user_id, contact.id
    )
    return compute_signals(contact, messages, notes, open_tasks, upcoming_events)


@router.get("/priority")
async def list_contact_priority(
    db: DbSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict]:
    """Contacts ranked by priority_score desc -- mirrors GET /goals/ready
    (goals/router.py): score every contact via 2 aggregate queries (never
    one per contact), rank in Python with the same pure scoring function
    the single-contact workspace uses, return the top `limit`. See
    CONTACT_INTELLIGENCE_ARCHITECTURE.md #12/#13.

    Registered on this router (not the generic `contacts_router`) so it can
    be mounted before that router's `/{item_id}` catch-all in main.py --
    otherwise "priority" would be parsed as `item_id` and 422 before ever
    reaching this route."""
    now = datetime.now(timezone.utc)
    settings = get_settings()

    contacts = await ContactRepository(db).list_for_intelligence(
        settings.contact_priority_candidate_ceiling
    )
    contact_ids = [contact.id for contact in contacts]

    overdue_counts = await TaskRepository(db).overdue_counts_by_contact(
        current_user.id, contact_ids, now=now
    )
    last_messages = await MessageRepository(db).last_message_by_contact(contact_ids)

    ranked: list[dict] = []
    for contact in contacts:
        last_message = last_messages.get(contact.id)
        signals = compute_risk_signals_from_aggregates(
            contact,
            overdue_task_count=overdue_counts.get(contact.id, 0),
            last_message_direction=last_message.direction if last_message else None,
            last_message_at=(
                (last_message.provider_timestamp or last_message.created_at)
                if last_message
                else None
            ),
            now=now,
        )
        primary_signal = primary_risk_signal(signals)
        ranked.append(
            {
                "contact_id": contact.id,
                "name": contact.name,
                "relationship_status": _relationship_status_dict(contact, signals),
                "suggested_next_action": suggested_next_action(signals),
                "last_interaction_at": contact.last_interaction_at,
                # Release 1.5 hardening: the frontend previously re-derived
                # this by sorting signals by severity client-side, which
                # could disagree with the backend's own priority ordering on
                # a tie (see contacts/intelligence.py::primary_risk_signal).
                # The frontend must only render this field now, never
                # recompute it.
                "primary_reason": primary_signal.reason if primary_signal else None,
            }
        )

    ranked.sort(key=lambda item: item["relationship_status"]["score"], reverse=True)
    return ranked[:limit]


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


def _relationship_status_dict(contact: Contact, signals: list[Signal]) -> dict:
    return {
        "tier": relationship_tier(contact, signals),
        "score": priority_score(signals),
        "signals": [
            {
                "code": signal.code,
                "kind": signal.kind,
                "severity": signal.severity,
                "reason": signal.reason,
            }
            for signal in signals
        ],
    }


def _recommendation_dict(recommendation: Recommendation) -> dict:
    return {
        "id": recommendation.id,
        "type": recommendation.type,
        "priority": recommendation.priority,
        "confidence": recommendation.confidence,
        "explanation": recommendation.explanation,
        "reasoning": recommendation.reasoning,
        "supporting_signals": recommendation.supporting_signals,
        "confirmation_required": recommendation.confirmation_required,
        "execution_target": recommendation.execution_target,
        "execution_payload": recommendation.execution_payload,
        "created_at": recommendation.created_at,
        "expires_at": recommendation.expires_at,
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
