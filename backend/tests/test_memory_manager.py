"""Memory Manager: facade for short-term, long-term, knowledge and preferences."""
from datetime import datetime, timedelta, timezone

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
async def test_short_term_orders_by_provider_timestamp_not_arrival_order(session_factory, contact):
    """A webhook redelivery or network jitter can insert an older message
    after a newer one; conversation history must stay chronological by the
    provider's own event time, not by insertion order."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with session_factory() as session:
        # Inserted out of chronological order: "terceira" (t+2) arrives first,
        # then "primeira" (t+0), then "segunda" (t+1).
        for text, offset in (("terceira", 2), ("primeira", 0), ("segunda", 1)):
            session.add(
                Message(
                    contact_id=contact.id,
                    direction=MessageDirection.INBOUND,
                    media_type=MessageMediaType.TEXT,
                    content=text,
                    provider_timestamp=base + timedelta(minutes=offset),
                )
            )
        await session.commit()

    async with session_factory() as session:
        history = await memory_manager.short_term(session, contact.id, limit=10)
    assert [m.content for m in history] == ["primeira", "segunda", "terceira"]


@pytest.mark.asyncio
async def test_short_term_falls_back_to_arrival_order_without_provider_timestamp(session_factory, contact):
    """Providers that don't report an event timestamp still get a sane,
    stable ordering (insertion order) via the coalesce to created_at/id."""
    async with session_factory() as session:
        for text in ("um", "dois", "tres"):
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
    assert [m.content for m in history] == ["um", "dois", "tres"]


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


@pytest.mark.asyncio
async def test_add_categories_appends_new_ones(session_factory, contact):
    async with session_factory() as session:
        added = await memory_manager.add_categories(session, contact.id, ["vip", "atacado"])
    assert added == ["vip", "atacado"]

    async with session_factory() as session:
        refreshed = await session.get(Contact, contact.id)
        assert refreshed.categories == ["vip", "atacado"]


@pytest.mark.asyncio
async def test_add_categories_skips_ones_already_present(session_factory, contact):
    """The docstring promises learning never writes the same fact twice."""
    async with session_factory() as session:
        await memory_manager.add_categories(session, contact.id, ["vip"])

    async with session_factory() as session:
        added = await memory_manager.add_categories(session, contact.id, ["vip", "novo"])
    assert added == ["novo"]

    async with session_factory() as session:
        refreshed = await session.get(Contact, contact.id)
        assert refreshed.categories == ["vip", "novo"]


@pytest.mark.asyncio
async def test_add_categories_all_already_present_is_a_no_op(session_factory, contact):
    async with session_factory() as session:
        await memory_manager.add_categories(session, contact.id, ["vip"])

    async with session_factory() as session:
        added = await memory_manager.add_categories(session, contact.id, ["vip"])
    assert added == []


@pytest.mark.asyncio
async def test_add_categories_unknown_contact_returns_empty_list(session_factory):
    async with session_factory() as session:
        assert await memory_manager.add_categories(session, 999999, ["vip"]) == []
