"""Coverage for /api/chat — the interactive AI chat endpoint.

One happy-path test already existed in test_agents.py
(test_chat_defaults_to_assistant_agent); this file builds out the rest —
auth, validation, agent selection, error handling, response shape — that
was missing for a router this central. Tests run with no real LLM key
configured (see conftest.py), so every response goes through the
provider's STUB_REPLY path rather than a real model call, same as the
existing agent tests in test_agents.py.
"""

import pytest

from providers.llm.base import STUB_REPLY


@pytest.mark.asyncio
async def test_chat_requires_authentication(client):
    response = await client.post("/api/chat", json={"message": "oi"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_defaults_to_assistant_agent(client, auth_headers):
    response = await client.post(
        "/api/chat", json={"message": "Bom dia"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["agent"] == "assistant"


@pytest.mark.asyncio
async def test_chat_response_shape(client, auth_headers):
    response = await client.post(
        "/api/chat", json={"message": "Bom dia"}, headers=auth_headers
    )
    body = response.json()
    assert set(body.keys()) == {"agent", "reply", "steps", "memories_used"}
    assert isinstance(body["reply"], str) and body["reply"]
    assert isinstance(body["steps"], list)
    assert isinstance(body["memories_used"], int)


@pytest.mark.asyncio
async def test_chat_returns_stub_reply_when_no_llm_key_configured(
    client, auth_headers
):
    """conftest.py sets OPENAI_API_KEY="" — no provider is enabled, so the
    reply must be the neutral stub, not a crash or an empty string."""
    response = await client.post(
        "/api/chat", json={"message": "Bom dia"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["reply"] == STUB_REPLY
    assert response.json()["steps"] == []


@pytest.mark.asyncio
async def test_chat_with_explicit_agent(client, auth_headers):
    response = await client.post(
        "/api/chat",
        json={"message": "Resuma meu dia", "agent": "personal"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["agent"] == "personal"


@pytest.mark.asyncio
async def test_chat_unknown_agent_returns_404(client, auth_headers):
    response = await client.post(
        "/api/chat",
        json={"message": "oi", "agent": "nope"},
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_with_contact_id_does_not_error(client, auth_headers):
    """contact_id is optional scoping for memory/history lookups, not a
    foreign-key validated field — an id with no matching Contact row must
    degrade gracefully (empty history/memories), not error."""
    response = await client.post(
        "/api/chat",
        json={"message": "oi", "contact_id": 999999},
        headers=auth_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_empty_message_rejected(client, auth_headers):
    response = await client.post(
        "/api/chat", json={"message": ""}, headers=auth_headers
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_missing_message_field_rejected(client, auth_headers):
    response = await client.post("/api/chat", json={}, headers=auth_headers)
    assert response.status_code == 422
