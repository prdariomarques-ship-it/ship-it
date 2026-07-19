import pytest


async def _register_and_login(client, email: str) -> dict[str, str]:
    """Bootstrap only — valid for the very first account in a fresh test DB
    (public registration is closed after that, see test_auth.py)."""
    await client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "User", "password": "supersecret1"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": "supersecret1"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _create_user_and_login(
    client, admin_headers: dict[str, str], email: str
) -> dict[str, str]:
    """Every account after the bootstrap admin must be admin-created —
    public `/auth/register` rejects a second registration outright."""
    await client.post(
        "/api/admin/users",
        json={"email": email, "full_name": "User", "password": "supersecret1"},
        headers=admin_headers,
    )
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": "supersecret1"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_admin_only_routes(client):
    admin_headers = await _register_and_login(client, "admin@example.com")  # first user
    user_headers = await _create_user_and_login(
        client, admin_headers, "user@example.com"
    )

    assert (await client.get("/api/logs", headers=admin_headers)).status_code == 200
    assert (await client.get("/api/logs", headers=user_headers)).status_code == 403

    assert (await client.get("/api/jobs", headers=admin_headers)).status_code == 200
    assert (await client.get("/api/jobs", headers=user_headers)).status_code == 403


@pytest.mark.asyncio
async def test_user_scoped_resources_are_isolated(client):
    admin_headers = await _register_and_login(client, "owner@example.com")
    other_headers = await _create_user_and_login(
        client, admin_headers, "other@example.com"
    )

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
