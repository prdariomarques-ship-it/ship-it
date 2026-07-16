import pytest


async def _register_and_login(client, email: str) -> dict[str, str]:
    await client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "User", "password": "supersecret1"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": "supersecret1"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_admin_only_routes(client):
    admin_headers = await _register_and_login(client, "admin@example.com")  # first user
    user_headers = await _register_and_login(client, "user@example.com")

    assert (await client.get("/api/logs", headers=admin_headers)).status_code == 200
    assert (await client.get("/api/logs", headers=user_headers)).status_code == 403

    assert (await client.get("/api/jobs", headers=admin_headers)).status_code == 200
    assert (await client.get("/api/jobs", headers=user_headers)).status_code == 403


@pytest.mark.asyncio
async def test_user_scoped_resources_are_isolated(client):
    admin_headers = await _register_and_login(client, "owner@example.com")
    other_headers = await _register_and_login(client, "other@example.com")

    created = await client.post(
        "/api/tasks", json={"title": "Minha tarefa"}, headers=admin_headers
    )
    task_id = created.json()["id"]

    assert (
        await client.get(f"/api/tasks/{task_id}", headers=admin_headers)
    ).status_code == 200
    assert (
        await client.get(f"/api/tasks/{task_id}", headers=other_headers)
    ).status_code == 404
    listed = await client.get("/api/tasks", headers=other_headers)
    assert listed.json() == []
