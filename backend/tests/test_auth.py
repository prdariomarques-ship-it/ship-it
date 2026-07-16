import pytest


@pytest.mark.asyncio
async def test_register_login_me_flow(client):
    register = await client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "full_name": "User",
            "password": "supersecret1",
        },
    )
    assert register.status_code == 201
    assert register.json()["email"] == "user@example.com"
    assert "hashed_password" not in register.json()

    login = await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "supersecret1"},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["refresh_token"]
    token = body["access_token"]

    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["full_name"] == "User"


@pytest.mark.asyncio
async def test_first_user_is_admin_second_is_not(client):
    first = await client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "full_name": "A", "password": "supersecret1"},
    )
    second = await client.post(
        "/api/auth/register",
        json={"email": "b@example.com", "full_name": "B", "password": "supersecret1"},
    )
    assert first.json()["role"] == "admin"
    assert second.json()["role"] == "user"


@pytest.mark.asyncio
async def test_refresh_token_rotation(client):
    await client.post(
        "/api/auth/register",
        json={"email": "rt@example.com", "full_name": "RT", "password": "supersecret1"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": "rt@example.com", "password": "supersecret1"}
    )
    refresh_token = login.json()["refresh_token"]

    refreshed = await client.post(
        "/api/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refreshed.status_code == 200
    new_pair = refreshed.json()
    assert new_pair["access_token"]
    assert new_pair["refresh_token"] != refresh_token

    # Rotation: the old refresh token is revoked and can't be reused.
    reused = await client.post(
        "/api/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert reused.status_code == 401

    # The new one works.
    again = await client.post(
        "/api/auth/refresh", json={"refresh_token": new_pair["refresh_token"]}
    )
    assert again.status_code == 200


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client):
    await client.post(
        "/api/auth/register",
        json={"email": "lo@example.com", "full_name": "LO", "password": "supersecret1"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": "lo@example.com", "password": "supersecret1"}
    )
    refresh_token = login.json()["refresh_token"]

    logout = await client.post(
        "/api/auth/logout", json={"refresh_token": refresh_token}
    )
    assert logout.status_code == 204

    refused = await client.post(
        "/api/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refused.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_email_rejected(client):
    payload = {
        "email": "dup@example.com",
        "full_name": "Dup",
        "password": "supersecret1",
    }
    assert (await client.post("/api/auth/register", json=payload)).status_code == 201
    assert (await client.post("/api/auth/register", json=payload)).status_code == 409


@pytest.mark.asyncio
async def test_wrong_password_rejected(client):
    await client.post(
        "/api/auth/register",
        json={"email": "wp@example.com", "full_name": "WP", "password": "supersecret1"},
    )
    login = await client.post(
        "/api/auth/login",
        json={"email": "wp@example.com", "password": "wrong-password"},
    )
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_requires_token(client):
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await client.get("/api/tasks")).status_code == 401
