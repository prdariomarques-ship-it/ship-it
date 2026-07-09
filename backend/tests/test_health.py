import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "Dario OS"


@pytest.mark.asyncio
async def test_openapi_available(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/auth/login" in response.json()["paths"]
