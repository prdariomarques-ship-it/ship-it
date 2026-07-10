"""MemoryService.delete / MemoryManager.forget — small additive extension
(Sprint 3) letting the Google Drive knowledge indexer replace a file's
stale chunks on re-indexing instead of accumulating duplicates forever.
Mocks the Qdrant client the same way `tests/test_providers.py` mocks httpx
for other providers — no real Qdrant server is reachable in this suite.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from memory.manager import memory_manager
from memory.service import memory_service
from models.embedding import Embedding


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _mock_qdrant(monkeypatch):
    client = MagicMock()
    client.delete = AsyncMock()
    monkeypatch.setattr(memory_service, "_client", client)
    monkeypatch.setattr(memory_service, "_collection_ready", True)
    yield client


async def _make_embedding(session_factory, vector_id: str, source: str = "knowledge") -> int:
    async with session_factory() as session:
        record = Embedding(source=source, content="conteúdo", vector_id=vector_id)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.id


@pytest.mark.asyncio
async def test_forget_deletes_qdrant_points_and_postgres_rows(session_factory, _mock_qdrant, db_engine):
    id_a = await _make_embedding(session_factory, "vec-a")
    id_b = await _make_embedding(session_factory, "vec-b")

    async with session_factory() as session:
        await memory_manager.forget(session, [id_a, id_b])

    _mock_qdrant.delete.assert_awaited_once()
    call_kwargs = _mock_qdrant.delete.call_args.kwargs
    assert set(call_kwargs["points_selector"]) == {"vec-a", "vec-b"}

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        remaining = (await session.execute(select(Embedding))).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_forget_leaves_other_embeddings_untouched(session_factory, _mock_qdrant, db_engine):
    to_delete = await _make_embedding(session_factory, "vec-delete")
    to_keep = await _make_embedding(session_factory, "vec-keep")

    async with session_factory() as session:
        await memory_manager.forget(session, [to_delete])

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        remaining = (await session.execute(select(Embedding))).scalars().all()
    assert [row.id for row in remaining] == [to_keep]


@pytest.mark.asyncio
async def test_forget_empty_list_is_a_no_op(session_factory, _mock_qdrant):
    async with session_factory() as session:
        await memory_manager.forget(session, [])
    _mock_qdrant.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_forget_unknown_ids_does_not_call_qdrant(session_factory, _mock_qdrant):
    async with session_factory() as session:
        await memory_manager.forget(session, [999999])
    _mock_qdrant.delete.assert_not_awaited()
