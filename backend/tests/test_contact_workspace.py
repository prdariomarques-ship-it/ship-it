"""GET /contacts/{id}/workspace -- Release 1.5, P0-2: Contact Workspace.

A single aggregate read over Notes/Tasks/Calendar/Messages/Memory, all
scoped to one contact, shaped exactly like the requested visual hierarchy:
`summary` (who/tags/last interaction -- `relationship_status`/
`suggested_next_action` are reserved `null` placeholders for P0-3),
`timeline` (WhatsApp+Notes+Tasks+Meetings merged, most recent first),
`current_state` (open_tasks/upcoming_events/pending_follow_ups/
important_notes), `recommendations` (always `[]` here -- P0-4's job).

Deliberately not testing any P0-3/P0-4 logic (scores, recommendations) --
those don't exist yet; every assertion here is about correctly assembling
data that already exists, never about producing a new judgment.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.calendar import CalendarEvent
from models.contact import Contact
from models.message import Message, MessageDirection
from models.note import Note
from models.task import Task, TaskPriority, TaskStatus
from models.user import User
from utils.config import get_settings


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _register_and_login(client) -> dict[str, str]:
    await client.post(
        "/api/auth/register",
        json={
            "email": "workspace@example.com",
            "full_name": "Owner",
            "password": "supersecret1",
        },
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": "workspace@example.com", "password": "supersecret1"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _owner_user(session_factory) -> User:
    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == "workspace@example.com")
        )
        return result.scalar_one()


async def _new_contact(session_factory, **kwargs) -> Contact:
    async with session_factory() as session:
        contact = Contact(**kwargs)
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact


# --- access control ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_contact_workspace_requires_authentication(client):
    response = await client.get("/api/contacts/1/workspace")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_contact_workspace_returns_404_for_unknown_contact(client):
    headers = await _register_and_login(client)
    response = await client.get("/api/contacts/999999/workspace", headers=headers)
    assert response.status_code == 404


# --- empty relationship -------------------------------------------------------------
@pytest.mark.asyncio
async def test_empty_relationship_returns_every_box_as_a_clean_empty_state(
    client, session_factory
):
    """A brand-new contact with nothing linked yet -- every list is empty,
    nothing crashes, the reserved P0-3/P0-4 fields stay null/empty."""
    headers = await _register_and_login(client)
    contact = await _new_contact(session_factory, name="Novo Contato")

    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    assert response.status_code == 200
    body = response.json()

    assert body["summary"]["relationship_status"] is None
    assert body["summary"]["suggested_next_action"] is None
    assert body["summary"]["ai_summary"] is None
    assert body["summary"]["last_interaction_at"] is None
    assert body["timeline"] == []
    assert body["current_state"] == {
        "open_tasks": [],
        "upcoming_events": [],
        "pending_follow_ups": [],
        "important_notes": [],
    }
    assert body["recommendations"] == []


# --- active relationship -------------------------------------------------------------
@pytest.mark.asyncio
async def test_active_relationship_populates_every_box(client, session_factory):
    """The opposite of the empty case: a contact with data in every
    source populates every box, all correctly scoped to this one contact."""
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(
        session_factory,
        name="Ana Souza",
        phone="+5511999990000",
        categories=["loja"],
        tags=["vip"],
        last_interaction_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
    )

    async with session_factory() as session:
        session.add_all(
            [
                Message(
                    contact_id=contact.id,
                    direction=MessageDirection.INBOUND,
                    content="Oi, tudo bem?",
                ),
                Message(
                    contact_id=contact.id,
                    direction=MessageDirection.OUTBOUND,
                    content="Tudo sim, e você?",
                ),
                Note(
                    user_id=owner.id,
                    title="Prefere contato à tarde",
                    content="x",
                    contact_id=contact.id,
                    pinned=True,
                ),
                Task(
                    user_id=owner.id,
                    title="Enviar orçamento",
                    contact_id=contact.id,
                    status=TaskStatus.PENDING,
                    priority=TaskPriority.MEDIUM,
                ),
                CalendarEvent(
                    user_id=owner.id,
                    title="Reunião de alinhamento",
                    contact_id=contact.id,
                    starts_at=datetime.now(timezone.utc) + timedelta(days=1),
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    body = response.json()

    assert body["summary"]["name"] == "Ana Souza"
    assert body["summary"]["last_interaction_at"] is not None
    assert len(body["current_state"]["open_tasks"]) == 1
    assert len(body["current_state"]["upcoming_events"]) == 1
    assert len(body["current_state"]["pending_follow_ups"]) == 1
    assert len(body["current_state"]["important_notes"]) == 1
    assert {"message", "note", "task", "meeting"} == {
        entry["type"] for entry in body["timeline"]
    }


# --- overdue follow-up ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_task_with_a_past_due_date_still_appears_correctly(
    client, session_factory
):
    """P0-2 doesn't compute an "overdue" flag (that's a P0-3 concept) --
    but a task whose due_date has already passed must still be assembled
    correctly, with its real due_date intact, not hidden or crashed on."""
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(session_factory, name="Contato com pendência")
    overdue_date = datetime.now(timezone.utc) - timedelta(days=10)

    async with session_factory() as session:
        session.add(
            Task(
                user_id=owner.id,
                title="Follow-up atrasado",
                contact_id=contact.id,
                status=TaskStatus.PENDING,
                priority=TaskPriority.HIGH,
                due_date=overdue_date,
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    open_tasks = response.json()["current_state"]["open_tasks"]
    assert len(open_tasks) == 1
    assert open_tasks[0]["title"] == "Follow-up atrasado"
    assert open_tasks[0]["due_date"] is not None


# --- no notes / no tasks / no meetings (each in isolation) --------------------------
@pytest.mark.asyncio
async def test_no_notes_but_other_boxes_populated(client, session_factory):
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(session_factory, name="Sem notas")
    async with session_factory() as session:
        session.add(
            Task(
                user_id=owner.id,
                title="Tarefa",
                contact_id=contact.id,
                status=TaskStatus.PENDING,
                priority=TaskPriority.MEDIUM,
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    body = response.json()
    assert body["current_state"]["important_notes"] == []
    assert len(body["current_state"]["open_tasks"]) == 1


@pytest.mark.asyncio
async def test_no_tasks_but_other_boxes_populated(client, session_factory):
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(session_factory, name="Sem tarefas")
    async with session_factory() as session:
        session.add(
            Note(
                user_id=owner.id,
                title="Nota",
                content="x",
                contact_id=contact.id,
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    body = response.json()
    assert body["current_state"]["open_tasks"] == []
    assert len(body["current_state"]["important_notes"]) == 1


@pytest.mark.asyncio
async def test_no_meetings_but_other_boxes_populated(client, session_factory):
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(session_factory, name="Sem reuniões")
    async with session_factory() as session:
        session.add(
            Note(
                user_id=owner.id,
                title="Nota",
                content="x",
                contact_id=contact.id,
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    body = response.json()
    assert body["current_state"]["upcoming_events"] == []
    assert not any(entry["type"] == "meeting" for entry in body["timeline"])


# --- isolation between contacts -----------------------------------------------------
@pytest.mark.asyncio
async def test_contact_workspace_includes_only_this_contacts_linked_data(
    client, session_factory
):
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)

    async with session_factory() as session:
        contact_a = Contact(name="Contato A", phone="+5511911110000")
        contact_b = Contact(name="Contato B", phone="+5511922220000")
        session.add_all([contact_a, contact_b])
        await session.commit()
        await session.refresh(contact_a)
        await session.refresh(contact_b)

        session.add_all(
            [
                Note(
                    user_id=owner.id,
                    title="Nota da Ana",
                    content="x",
                    contact_id=contact_a.id,
                ),
                Note(
                    user_id=owner.id,
                    title="Nota de outro contato",
                    content="x",
                    contact_id=contact_b.id,
                ),
                Note(user_id=owner.id, title="Nota sem contato", content="x"),
                Task(
                    user_id=owner.id,
                    title="Tarefa da Ana",
                    contact_id=contact_a.id,
                    status=TaskStatus.PENDING,
                    priority=TaskPriority.MEDIUM,
                ),
                Task(
                    user_id=owner.id,
                    title="Tarefa de outro contato",
                    contact_id=contact_b.id,
                    status=TaskStatus.PENDING,
                    priority=TaskPriority.MEDIUM,
                ),
                CalendarEvent(
                    user_id=owner.id,
                    title="Reunião com a Ana",
                    contact_id=contact_a.id,
                    starts_at=datetime.now(timezone.utc) + timedelta(days=1),
                ),
                CalendarEvent(
                    user_id=owner.id,
                    title="Reunião com outro contato",
                    contact_id=contact_b.id,
                    starts_at=datetime.now(timezone.utc) + timedelta(days=1),
                ),
            ]
        )
        await session.commit()
        contact_a_id = contact_a.id

    response = await client.get(
        f"/api/contacts/{contact_a_id}/workspace", headers=headers
    )
    assert response.status_code == 200
    body = response.json()

    assert [n["title"] for n in body["current_state"]["important_notes"]] == [
        "Nota da Ana"
    ]
    assert [t["title"] for t in body["current_state"]["open_tasks"]] == [
        "Tarefa da Ana"
    ]
    assert [e["title"] for e in body["current_state"]["upcoming_events"]] == [
        "Reunião com a Ana"
    ]


# --- large timeline ordering ---------------------------------------------------------
@pytest.mark.asyncio
async def test_large_timeline_stays_chronologically_ordered_and_capped(
    client, session_factory
):
    """20 messages + 10 notes + 5 tasks + 5 meetings (40 entries total,
    well past the internal cap) -- the merged timeline must still come
    back strictly newest-first and capped, never just "whatever order the
    four sources happened to return."""
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(session_factory, name="Linha do tempo longa")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    async with session_factory() as session:
        for i in range(20):
            session.add(
                Message(
                    contact_id=contact.id,
                    direction=MessageDirection.INBOUND,
                    content=f"mensagem {i}",
                    provider_timestamp=base + timedelta(hours=i),
                )
            )
        await session.commit()

        for i in range(10):
            note = Note(
                user_id=owner.id,
                title=f"nota {i}",
                content="x",
                contact_id=contact.id,
            )
            session.add(note)
        await session.commit()

        for i in range(5):
            session.add(
                Task(
                    user_id=owner.id,
                    title=f"tarefa {i}",
                    contact_id=contact.id,
                    status=TaskStatus.PENDING,
                    priority=TaskPriority.MEDIUM,
                )
            )
        await session.commit()

        for i in range(5):
            session.add(
                CalendarEvent(
                    user_id=owner.id,
                    title=f"reunião {i}",
                    contact_id=contact.id,
                    starts_at=base + timedelta(days=i),
                )
            )
        await session.commit()

    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    timeline = response.json()["timeline"]

    # Capped -- never just returns everything unbounded.
    assert len(timeline) <= 30
    # Strictly newest-first across all four merged sources.
    timestamps = [entry["timestamp"] for entry in timeline]
    assert timestamps == sorted(timestamps, reverse=True)


# --- missing optional fields ----------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_optional_contact_fields_render_without_error(
    client, session_factory
):
    """A contact with no phone, no categories, no tags, never contacted --
    every optional field is genuinely absent, not just empty-string; the
    endpoint must still respond cleanly."""
    headers = await _register_and_login(client)
    contact = await _new_contact(session_factory, name="Só o nome mesmo")

    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["phone"] is None
    assert body["summary"]["categories"] == []
    assert body["summary"]["tags"] == []
    assert body["summary"]["last_interaction_at"] is None
    assert body["summary"]["ai_summary"] is None


# --- timeline contract ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_timeline_entry_follows_the_stable_contract(client, session_factory):
    """Every timeline entry -- regardless of source -- exposes exactly the
    same keys (id/type/timestamp/title/subtitle/status/source/metadata),
    so the frontend never has to branch on which module produced it, and a
    future source (Email, Calls, Documents...) can slot in unchanged."""
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(session_factory, name="Contrato do timeline")
    async with session_factory() as session:
        session.add(
            Note(
                user_id=owner.id,
                title="Nota",
                content="conteúdo",
                contact_id=contact.id,
                pinned=True,
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    timeline = response.json()["timeline"]
    assert len(timeline) == 1
    entry = timeline[0]
    assert set(entry.keys()) == {
        "id",
        "type",
        "timestamp",
        "title",
        "subtitle",
        "status",
        "source",
        "metadata",
    }
    assert entry["type"] == "note"
    assert entry["source"] == "notes"
    assert entry["status"] == "pinned"
    assert entry["metadata"] == {"pinned": True}


@pytest.mark.asyncio
async def test_timeline_with_only_one_source_populated(client, session_factory):
    """A contact with data in exactly one source (no notes/tasks/meetings,
    only messages) -- the timeline must contain only that source's
    entries, correctly shaped, not crash on the other three being empty."""
    headers = await _register_and_login(client)
    contact = await _new_contact(session_factory, name="Só mensagens")
    async with session_factory() as session:
        session.add(
            Message(
                contact_id=contact.id,
                direction=MessageDirection.INBOUND,
                content="Oi",
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    timeline = response.json()["timeline"]
    assert len(timeline) == 1
    assert timeline[0]["type"] == "message"
    assert timeline[0]["source"] == "whatsapp"


# --- deterministic ordering / equal timestamps -----------------------------------------
@pytest.mark.asyncio
async def test_timeline_breaks_ties_on_equal_timestamps_deterministically(
    client, session_factory
):
    """Two notes created at the exact same instant must still come back in
    a stable, reproducible order -- never left to incidental DB/Python
    ordering. The endpoint tie-breaks on (type, id) descending; asserting
    a fixed order here pins that contract down, not just "some order"."""
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(session_factory, name="Timestamps iguais")
    same_instant = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)

    async with session_factory() as session:
        note_a = Note(
            user_id=owner.id,
            title="Primeira nota",
            content="x",
            contact_id=contact.id,
            created_at=same_instant,
        )
        session.add(note_a)
        await session.commit()
        await session.refresh(note_a)

    async with session_factory() as session:
        note_b = Note(
            user_id=owner.id,
            title="Segunda nota",
            content="x",
            contact_id=contact.id,
            created_at=same_instant,
        )
        session.add(note_b)
        await session.commit()
        await session.refresh(note_b)

    response_1 = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    response_2 = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    note_ids_1 = [
        e["id"] for e in response_1.json()["timeline"] if e["type"] == "note"
    ]
    note_ids_2 = [
        e["id"] for e in response_2.json()["timeline"] if e["type"] == "note"
    ]
    # Same order on repeated requests -- not just "some" order each time.
    assert note_ids_1 == note_ids_2
    # Deterministic tie-break: higher id (created later) sorts first.
    assert note_ids_1 == [f"note-{note_b.id}", f"note-{note_a.id}"]


# --- configurable timeline limit --------------------------------------------------------
@pytest.mark.asyncio
async def test_timeline_limit_is_configurable(client, session_factory, monkeypatch):
    """The combined-timeline cap comes from Settings
    (`contact_workspace_timeline_limit`), not a hardcoded constant --
    changing it at runtime changes what the endpoint returns, with no
    code change required."""
    monkeypatch.setattr(get_settings(), "contact_workspace_timeline_limit", 2)
    headers = await _register_and_login(client)
    owner = await _owner_user(session_factory)
    contact = await _new_contact(session_factory, name="Limite configurável")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with session_factory() as session:
        for i in range(5):
            session.add(
                Note(
                    user_id=owner.id,
                    title=f"nota {i}",
                    content="x",
                    contact_id=contact.id,
                    created_at=base + timedelta(hours=i),
                )
            )
        await session.commit()

    response = await client.get(
        f"/api/contacts/{contact.id}/workspace", headers=headers
    )
    assert len(response.json()["timeline"]) == 2
