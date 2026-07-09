import pytest


@pytest.mark.asyncio
async def test_register_login_me_flow(client):
    register = await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "full_name": "User", "password": "supersecret1"},
    )
    assert register.status_code == 201
    assert register.json()["email"] == "user@example.com"
    assert "hashed_password" not in register.json()

    login = await client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "supersecret1"}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["full_name"] == "User"


@pytest.mark.asyncio
async def test_duplicate_email_rejected(client):
    payload = {"email": "dup@example.com", "full_name": "Dup", "password": "supersecret1"}
    assert (await client.post("/api/auth/register", json=payload)).status_code == 201
    assert (await client.post("/api/auth/register", json=payload)).status_code == 409


@pytest.mark.asyncio
async def test_wrong_password_rejected(client):
    await client.post(
        "/api/auth/register",
        json={"email": "wp@example.com", "full_name": "WP", "password": "supersecret1"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": "wp@example.com", "password": "wrong-password"}
    )
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_requires_token(client):
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await client.get("/api/tasks")).status_code == 401
