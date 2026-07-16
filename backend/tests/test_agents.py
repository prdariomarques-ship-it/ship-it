import pytest


@pytest.mark.asyncio
async def test_list_agents(client, auth_headers):
    response = await client.get("/api/agents", headers=auth_headers)
    assert response.status_code == 200
    agents = {agent["name"]: agent for agent in response.json()}
    assert set(agents) == {"personal", "church", "store", "content", "assistant"}
    assert "create_task" in agents["personal"]["tools"]
    assert "send_whatsapp_message" in agents["assistant"]["tools"]


@pytest.mark.asyncio
async def test_run_agent_without_llm_key_returns_stub(client, auth_headers):
    response = await client.post(
        "/api/agents/personal/run",
        json={"message": "Resuma meu dia"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["agent"] == "personal"
    assert response.json()["reply"]  # stub reply when no API key
    assert response.json()["steps"] == []


@pytest.mark.asyncio
async def test_run_unknown_agent_returns_404(client, auth_headers):
    response = await client.post(
        "/api/agents/nope/run", json={"message": "oi"}, headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_chat_defaults_to_assistant_agent(client, auth_headers):
    response = await client.post(
        "/api/chat", json={"message": "Bom dia"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["agent"] == "assistant"
