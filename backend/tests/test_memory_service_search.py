"""MemoryService.search — regression test for a Sprint 5 audit finding:
the installed qdrant-client (>=1.12,<2, resolves to 1.18.0) removed
`AsyncQdrantClient.search()` in favor of `query_points()`. The old call
raised `AttributeError` on every semantic-search request in production.
Mocks the Qdrant client the same way `test_memory_service_delete.py` does
— no real Qdrant server is reachable in this suite.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client.http.models.models import QueryResponse, ScoredPoint

import memory.service as memory_service_module
from memory.manager import memory_manager
from memory.service import memory_service


@pytest.fixture(autouse=True)
def _mock_qdrant(monkeypatch):
    client = MagicMock()
    point = ScoredPoint(
        id="vec-a",
        version=0,
        score=0.9,
        payload={"content": "Prefere atendimento pela manhã", "source": "whatsapp", "contact_id": 1},
        vector=None,
    )
    client.query_points = AsyncMock(return_value=QueryResponse(points=[point]))
    monkeypatch.setattr(memory_service, "_client", client)
    monkeypatch.setattr(memory_service, "_collection_ready", True)

    embedding_provider = MagicMock()
    embedding_provider.embed = AsyncMock(return_value=[0.1] * 1536)
    monkeypatch.setattr(memory_service_module, "get_embedding_provider", lambda: embedding_provider)

    yield client


@pytest.mark.asyncio
async def test_search_calls_query_points_not_the_removed_search_method(_mock_qdrant):
    results = await memory_service.search("atendimento", limit=5, contact_id=1)

    _mock_qdrant.query_points.assert_awaited_once()
    assert not hasattr(_mock_qdrant, "search") or not _mock_qdrant.search.called
    assert results == [
        {"content": "Prefere atendimento pela manhã", "source": "whatsapp", "contact_id": 1, "score": 0.9}
    ]


@pytest.mark.asyncio
async def test_search_passes_query_vector_via_query_kwarg(_mock_qdrant):
    await memory_service.search("atendimento", limit=3)

    call_kwargs = _mock_qdrant.query_points.call_args.kwargs
    assert "query" in call_kwargs
    assert call_kwargs["limit"] == 3


@pytest.mark.asyncio
async def test_long_term_search_returns_results_from_query_points(_mock_qdrant):
    hits = await memory_manager.long_term_search("atendimento", contact_id=1, limit=5)
    assert len(hits) == 1
    assert hits[0]["content"] == "Prefere atendimento pela manhã"
