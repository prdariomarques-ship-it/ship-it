import pytest


@pytest.mark.asyncio
async def test_list_agents(client, auth_headers):
    response = await client.get("/api/agents", headers=auth_headers)
    assert response.status_code == 200
    names = {agent["name"] for agent in response.json()}
    assert names == {"personal", "whatsapp", "church", "store", "content"}


@pytest.mark.asyncio
async def test_run_agent_without_openai_key_returns_stub(client, auth_headers):
    response = await client.post(
        "/api/agents/personal/run", json={"message": "Resuma meu dia"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["agent"] == "personal"
    assert response.json()["reply"]  # stub reply when no API key


@pytest.mark.asyncio
async def test_run_unknown_agent_returns_404(client, auth_headers):
    response = await client.post(
        "/api/agents/nope/run", json={"message": "oi"}, headers=auth_headers
    )
    assert response.status_code == 404
