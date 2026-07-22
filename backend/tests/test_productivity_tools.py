"""agents/tools/productivity.py -- contact_id auto-linking (Release 1.5,
P0-2: Contact Workspace). `create_task`/`create_calendar_event`/
`create_note` now persist `ToolContext.contact_id` when the call happens
inside a WhatsApp conversation, so the Contact Workspace's Notes/Tasks/
Upcoming events boxes populate without any extra judgment from the model.
`contact_id=None` (e.g. an admin-triggered call, no conversation) must
behave exactly as before this change.
"""

import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from agents.tools.base import ToolContext
from agents.tools.productivity import (
    create_event_tool,
    create_note_tool,
    create_task_tool,
)
from models.contact import Contact
from models.user import User


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def user(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="prod@example.com", full_name="U", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def contact(session_factory) -> Contact:
    async with session_factory() as session:
        contact = Contact(name="Ana", phone="+5511999990000")
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact


@pytest.mark.asyncio
async def test_create_task_links_the_conversations_contact(
    session_factory, user, contact
):
    async with session_factory() as session:
        result = await create_task_tool.run(
            ToolContext(db=session, user=user, contact_id=contact.id),
            {"title": "Enviar orçamento"},
        )
    payload = json.loads(result)
    assert payload["ok"] is True

    async with session_factory() as session:
        from repositories.task import TaskRepository

        tasks = await TaskRepository(session).list(user_id=user.id)
    assert tasks[0].contact_id == contact.id


@pytest.mark.asyncio
async def test_create_task_outside_a_conversation_leaves_contact_id_unset(
    session_factory, user
):
    async with session_factory() as session:
        await create_task_tool.run(
            ToolContext(db=session, user=user, contact_id=None),
            {"title": "Tarefa administrativa"},
        )
    async with session_factory() as session:
        from repositories.task import TaskRepository

        tasks = await TaskRepository(session).list(user_id=user.id)
    assert tasks[0].contact_id is None


@pytest.mark.asyncio
async def test_create_calendar_event_links_the_conversations_contact(
    session_factory, user, contact
):
    async with session_factory() as session:
        result = await create_event_tool.run(
            ToolContext(db=session, user=user, contact_id=contact.id),
            {"title": "Reunião", "starts_at": "2026-08-01T10:00:00"},
        )
    assert json.loads(result)["ok"] is True

    async with session_factory() as session:
        from repositories.base import SQLAlchemyRepository
        from models.calendar import CalendarEvent

        class _Repo(SQLAlchemyRepository[CalendarEvent]):
            model = CalendarEvent

        events = await _Repo(session).list(user_id=user.id)
    assert events[0].contact_id == contact.id


@pytest.mark.asyncio
async def test_create_note_links_the_conversations_contact(
    session_factory, user, contact
):
    async with session_factory() as session:
        result = await create_note_tool.run(
            ToolContext(db=session, user=user, contact_id=contact.id),
            {"title": "Prefere contato à tarde"},
        )
    assert json.loads(result)["ok"] is True

    async with session_factory() as session:
        from repositories.note import NoteRepository

        notes = await NoteRepository(session).list(user_id=user.id)
    assert notes[0].contact_id == contact.id


@pytest.mark.asyncio
async def test_create_note_outside_a_conversation_leaves_contact_id_unset(
    session_factory, user
):
    async with session_factory() as session:
        await create_note_tool.run(
            ToolContext(db=session, user=user, contact_id=None),
            {"title": "Nota administrativa"},
        )
    async with session_factory() as session:
        from repositories.note import NoteRepository

        notes = await NoteRepository(session).list(user_id=user.id)
    assert notes[0].contact_id is None
