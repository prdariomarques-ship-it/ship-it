"""PROD-005: technical isolation for cross-contact tools.

`send_whatsapp_message` and `find_contact` must never act on a contact other
than the one the current conversation is scoped to — enforced in code via
`ToolContext.contact_id` (set by `BaseAgent.run` from application state, never
from the LLM), not by a prompt instruction. These tests simulate a malicious
or careless tool-call argument (as if injected by a manipulated LLM) and
confirm the handler itself rejects it regardless of what the model asked for.
"""
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from agents.tools.base import ToolContext
from agents.tools.communication import find_contact_tool, send_whatsapp_tool
from models.contact import Contact
from models.job import Job
from models.user import User


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def user(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="isolation@example.com", full_name="Isolation", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def contact_a(session_factory) -> Contact:
    async with session_factory() as session:
        contact = Contact(name="Contato A", phone="5511900000001")
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact


@pytest.fixture
async def contact_b(session_factory) -> Contact:
    async with session_factory() as session:
        contact = Contact(name="Contato B", phone="5511900000002")
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact


# --- send_whatsapp_message ---------------------------------------------------
@pytest.mark.asyncio
async def test_send_blocks_message_to_another_contact_when_conversation_scoped(
    session_factory, user, contact_a, contact_b
):
    """Contact A's conversation must not be able to message Contact B —
    simulates a prompt-injected/malicious `to` argument."""
    async with session_factory() as session:
        context = ToolContext(db=session, user=user, contact_id=contact_a.id)
        result = await send_whatsapp_tool.run(context, {"to": contact_b.phone, "message": "oi"})

    payload = json.loads(result)
    assert "error" in payload
    assert "not authorized" in payload["error"]

    async with session_factory() as session:
        jobs = (await session.execute(select(Job))).scalars().all()
    assert jobs == []  # nothing was queued


@pytest.mark.asyncio
async def test_send_allows_message_to_the_current_conversation_contact(session_factory, user, contact_a):
    async with session_factory() as session:
        context = ToolContext(db=session, user=user, contact_id=contact_a.id)
        result = await send_whatsapp_tool.run(context, {"to": contact_a.phone, "message": "oi"})

    payload = json.loads(result)
    assert payload["ok"] is True

    async with session_factory() as session:
        jobs = (await session.execute(select(Job))).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].payload["to"] == contact_a.phone


@pytest.mark.asyncio
async def test_send_allows_message_to_a_known_contact_without_conversation_scope(
    session_factory, user, contact_a
):
    """No contact_id (e.g. an admin using the dashboard/chat directly, not a
    WhatsApp-triggered run) — sending to an existing, known contact is fine."""
    async with session_factory() as session:
        context = ToolContext(db=session, user=user, contact_id=None)
        result = await send_whatsapp_tool.run(context, {"to": contact_a.phone, "message": "oi"})

    payload = json.loads(result)
    assert payload["ok"] is True


@pytest.mark.asyncio
async def test_send_blocks_arbitrary_unknown_number_without_conversation_scope(session_factory, user):
    """Without a conversation scope, the model still cannot invent a brand
    new destination number that isn't a known contact."""
    async with session_factory() as session:
        context = ToolContext(db=session, user=user, contact_id=None)
        result = await send_whatsapp_tool.run(context, {"to": "5599999999999", "message": "oi"})

    payload = json.loads(result)
    assert "error" in payload

    async with session_factory() as session:
        jobs = (await session.execute(select(Job))).scalars().all()
    assert jobs == []


@pytest.mark.asyncio
async def test_send_isolation_is_not_bypassable_by_phone_formatting(session_factory, user, contact_a, contact_b):
    """Normalizing the target phone (e.g. adding '@c.us' or '+') must not
    let a scoped conversation slip past the isolation check."""
    async with session_factory() as session:
        context = ToolContext(db=session, user=user, contact_id=contact_a.id)
        result = await send_whatsapp_tool.run(
            context, {"to": f"+{contact_b.phone}@c.us", "message": "oi"}
        )

    payload = json.loads(result)
    assert "error" in payload


# --- find_contact --------------------------------------------------------------
@pytest.mark.asyncio
async def test_find_contact_blocks_lookup_of_another_contact_when_conversation_scoped(
    session_factory, user, contact_a, contact_b
):
    async with session_factory() as session:
        context = ToolContext(db=session, user=user, contact_id=contact_a.id)
        result = await find_contact_tool.run(context, {"query": contact_b.name})

    payload = json.loads(result)
    assert "error" in payload
    assert "not authorized" in payload["error"]


@pytest.mark.asyncio
async def test_find_contact_blocks_lookup_by_phone_of_another_contact(session_factory, user, contact_a, contact_b):
    async with session_factory() as session:
        context = ToolContext(db=session, user=user, contact_id=contact_a.id)
        result = await find_contact_tool.run(context, {"query": contact_b.phone})

    payload = json.loads(result)
    assert "error" in payload


@pytest.mark.asyncio
async def test_find_contact_allows_lookup_of_the_current_conversation_contact(session_factory, user, contact_a):
    async with session_factory() as session:
        context = ToolContext(db=session, user=user, contact_id=contact_a.id)
        result = await find_contact_tool.run(context, {"query": contact_a.phone})

    payload = json.loads(result)
    assert payload["found"] is True
    assert payload["contact"]["id"] == contact_a.id


@pytest.mark.asyncio
async def test_find_contact_open_lookup_preserved_without_conversation_scope(
    session_factory, user, contact_a, contact_b
):
    """No contact_id — the existing admin/dashboard lookup behavior is
    unchanged: any contact can be found."""
    async with session_factory() as session:
        context = ToolContext(db=session, user=user, contact_id=None)
        result = await find_contact_tool.run(context, {"query": contact_b.name})

    payload = json.loads(result)
    assert payload["found"] is True
    assert payload["contact"]["id"] == contact_b.id


@pytest.mark.asyncio
async def test_find_contact_scoped_query_with_no_match_is_denied_not_leaked_as_not_found(
    session_factory, user, contact_a
):
    """A query that matches nothing, from a scoped conversation, still comes
    back as a denial (not a plain 'not found') — it must not distinguish
    'no such contact' from 'that's someone else's contact' to the model."""
    async with session_factory() as session:
        context = ToolContext(db=session, user=user, contact_id=contact_a.id)
        result = await find_contact_tool.run(context, {"query": "Nome Que Não Existe"})

    payload = json.loads(result)
    assert "error" in payload
