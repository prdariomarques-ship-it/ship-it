"""Memory Manager: facade for short-term, long-term, knowledge and preferences."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from memory.manager import memory_manager
from models.contact import Contact
from models.message import Message, MessageDirection, MessageMediaType


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def contact(session_factory) -> Contact:
    async with session_factory() as session:
        contact = Contact(name="Maria", phone="5511977770000")
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact


@pytest.mark.asyncio
async def test_short_term_returns_recent_messages_oldest_first(session_factory, contact):
    async with session_factory() as session:
        for text in ("primeira", "segunda", "terceira"):
            session.add(
                Message(
                    contact_id=contact.id,
                    direction=MessageDirection.INBOUND,
                    media_type=MessageMediaType.TEXT,
                    content=text,
                )
            )
        await session.commit()

    async with session_factory() as session:
        history = await memory_manager.short_term(session, contact.id, limit=10)
    assert [m.content for m in history] == ["primeira", "segunda", "terceira"]


@pytest.mark.asyncio
async def test_preferences_round_trip(session_factory, contact):
    async with session_factory() as session:
        preferences = await memory_manager.set_preference(
            session, contact.id, "horario_entrega", "tarde"
        )
    assert preferences == {"horario_entrega": "tarde"}

    async with session_factory() as session:
        stored = await memory_manager.get_preferences(session, contact.id)
    assert stored == {"horario_entrega": "tarde"}


@pytest.mark.asyncio
async def test_set_preference_merges_without_clobbering_existing_keys(session_factory, contact):
    async with session_factory() as session:
        await memory_manager.set_preference(session, contact.id, "a", "1")
    async with session_factory() as session:
        merged = await memory_manager.set_preference(session, contact.id, "b", "2")
    assert merged == {"a": "1", "b": "2"}


@pytest.mark.asyncio
async def test_set_preference_unknown_contact_raises(session_factory):
    async with session_factory() as session:
        with pytest.raises(ValueError):
            await memory_manager.set_preference(session, 999999, "a", "1")


@pytest.mark.asyncio
async def test_get_preferences_unknown_contact_returns_empty_dict(session_factory):
    async with session_factory() as session:
        assert await memory_manager.get_preferences(session, 999999) == {}
