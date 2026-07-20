import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from auth.service import AuthError, AuthService
from repositories.password_reset_token import PasswordResetTokenRepository
from repositories.user import UserRepository


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


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
async def test_bootstrap_registration_allowed_and_becomes_admin(client):
    """The very first account, and only the very first, may self-register
    through the public endpoint — and it always becomes admin."""
    first = await client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "full_name": "A", "password": "supersecret1"},
    )
    assert first.status_code == 201
    assert first.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_second_public_registration_denied(client):
    """Once an account exists, public self-registration is closed — closes
    the gap where anyone finding the login page could self-provision an
    account with access to shared data (messages, contacts, church, store)."""
    await client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "full_name": "A", "password": "supersecret1"},
    )
    second = await client.post(
        "/api/auth/register",
        json={"email": "b@example.com", "full_name": "B", "password": "supersecret1"},
    )
    assert second.status_code == 403

    # And the rejected account was never created — it can't log in either.
    login = await client.post(
        "/api/auth/login", json={"email": "b@example.com", "password": "supersecret1"}
    )
    assert login.status_code == 401


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
    """Duplicate-email detection now only matters on the admin-created path
    — the public path always rejects a second registration outright,
    regardless of email, before this check would ever run."""
    admin_headers = await _bootstrap_admin(client)
    payload = {
        "email": "dup@example.com",
        "full_name": "Dup",
        "password": "supersecret1",
    }
    first = await client.post("/api/admin/users", json=payload, headers=admin_headers)
    assert first.status_code == 201
    second = await client.post("/api/admin/users", json=payload, headers=admin_headers)
    assert second.status_code == 409


async def _bootstrap_admin(client) -> dict[str, str]:
    await client.post(
        "/api/auth/register",
        json={
            "email": "admin@example.com",
            "full_name": "Admin",
            "password": "supersecret1",
        },
    )
    login = await client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "supersecret1"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_admin_created_user_succeeds(client):
    admin_headers = await _bootstrap_admin(client)

    created = await client.post(
        "/api/admin/users",
        json={
            "email": "newuser@example.com",
            "full_name": "New User",
            "password": "supersecret1",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["email"] == "newuser@example.com"
    assert body["role"] == "user"  # default role, not admin
    assert "hashed_password" not in body

    # And the created account can actually log in.
    login = await client.post(
        "/api/auth/login",
        json={"email": "newuser@example.com", "password": "supersecret1"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_non_admin_cannot_create_user(client):
    # A second account can only come from the admin endpoint now — use it to
    # create a plain user, then prove that user can't use the same endpoint.
    admin_headers = await _bootstrap_admin(client)
    created = await client.post(
        "/api/admin/users",
        json={
            "email": "plainuser@example.com",
            "full_name": "Plain User",
            "password": "supersecret1",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201

    user_login = await client.post(
        "/api/auth/login",
        json={"email": "plainuser@example.com", "password": "supersecret1"},
    )
    user_headers = {
        "Authorization": f"Bearer {user_login.json()['access_token']}"
    }

    denied = await client.post(
        "/api/admin/users",
        json={
            "email": "shouldnotexist@example.com",
            "full_name": "Should Not Exist",
            "password": "supersecret1",
        },
        headers=user_headers,
    )
    assert denied.status_code == 403


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


@pytest.mark.asyncio
async def test_change_password_then_login_with_new_password(client):
    await client.post(
        "/api/auth/register",
        json={"email": "cp@example.com", "full_name": "CP", "password": "supersecret1"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": "cp@example.com", "password": "supersecret1"}
    )
    token = login.json()["access_token"]

    changed = await client.post(
        "/api/auth/change-password",
        json={"current_password": "supersecret1", "new_password": "newsecret2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert changed.status_code == 204

    old_login = await client.post(
        "/api/auth/login", json={"email": "cp@example.com", "password": "supersecret1"}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/auth/login", json={"email": "cp@example.com", "password": "newsecret2"}
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_change_password_rejects_wrong_current_password(client):
    await client.post(
        "/api/auth/register",
        json={"email": "cpw@example.com", "full_name": "CPW", "password": "supersecret1"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": "cpw@example.com", "password": "supersecret1"}
    )
    token = login.json()["access_token"]

    changed = await client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong-password", "new_password": "newsecret2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert changed.status_code == 401

    # Old password still works — nothing was changed.
    still_works = await client.post(
        "/api/auth/login", json={"email": "cpw@example.com", "password": "supersecret1"}
    )
    assert still_works.status_code == 200


@pytest.mark.asyncio
async def test_change_password_requires_authentication(client):
    response = await client.post(
        "/api/auth/change-password",
        json={"current_password": "x", "new_password": "newsecret2"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_change_password_revokes_other_sessions(client):
    """A refresh token issued before the change must stop working — a
    leaked/lost password shouldn't keep granting access through a session
    opened before it was changed."""
    await client.post(
        "/api/auth/register",
        json={"email": "cprt@example.com", "full_name": "CPRT", "password": "supersecret1"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": "cprt@example.com", "password": "supersecret1"}
    )
    token = login.json()["access_token"]
    old_refresh_token = login.json()["refresh_token"]

    changed = await client.post(
        "/api/auth/change-password",
        json={"current_password": "supersecret1", "new_password": "newsecret2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert changed.status_code == 204

    refreshed = await client.post(
        "/api/auth/refresh", json={"refresh_token": old_refresh_token}
    )
    assert refreshed.status_code == 401


# --- Forgot password / reset password -----------------------------------------
@pytest.mark.asyncio
async def test_forgot_password_returns_204_for_an_existing_email(client):
    await client.post(
        "/api/auth/register",
        json={"email": "fp@example.com", "full_name": "FP", "password": "supersecret1"},
    )
    response = await client.post(
        "/api/auth/forgot-password", json={"email": "fp@example.com"}
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_forgot_password_returns_204_for_a_nonexistent_email(client):
    """Same status code whether or not the email matches an account --
    otherwise the endpoint itself would leak which emails have accounts."""
    response = await client.post(
        "/api/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_forgot_password_logs_a_usable_reset_token(session_factory):
    async with session_factory() as session:
        user = await UserRepository(session).create(
            email="logtoken@example.com",
            full_name="Log Token",
            hashed_password="x",
        )

    with patch("auth.service.logger") as mock_logger:
        async with session_factory() as session:
            await AuthService(session).request_password_reset("logtoken@example.com")
        assert mock_logger.warning.called
        logged_token = mock_logger.warning.call_args[0][3]

    async with session_factory() as session:
        await AuthService(session).reset_password(logged_token, "brandnewpass1")

    async with session_factory() as session:
        refreshed = await UserRepository(session).get(user.id)
    from auth.password import verify_password

    assert verify_password("brandnewpass1", refreshed.hashed_password)


@pytest.mark.asyncio
async def test_forgot_password_does_not_log_for_a_nonexistent_email(session_factory):
    with patch("auth.service.logger") as mock_logger:
        async with session_factory() as session:
            await AuthService(session).request_password_reset("nobody@example.com")
        assert not mock_logger.warning.called


@pytest.mark.asyncio
async def test_reset_password_with_bogus_token_is_rejected(client):
    response = await client.post(
        "/api/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "brandnewpass1"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_reset_password_token_cannot_be_reused(session_factory):
    async with session_factory() as session:
        await UserRepository(session).create(
            email="reuse@example.com", full_name="Reuse", hashed_password="x"
        )

    with patch("auth.service.logger") as mock_logger:
        async with session_factory() as session:
            await AuthService(session).request_password_reset("reuse@example.com")
        token = mock_logger.warning.call_args[0][3]

    async with session_factory() as session:
        await AuthService(session).reset_password(token, "firstnewpass1")

    async with session_factory() as session:
        with pytest.raises(AuthError):
            await AuthService(session).reset_password(token, "secondnewpass1")


@pytest.mark.asyncio
async def test_reset_password_with_expired_token_is_rejected(session_factory):
    async with session_factory() as session:
        user = await UserRepository(session).create(
            email="expired@example.com", full_name="Expired", hashed_password="x"
        )
        expired_record = await PasswordResetTokenRepository(session).create(
            user_id=user.id,
            token_hash=hashlib.sha256(b"expired-token").hexdigest(),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

    async with session_factory() as session:
        with pytest.raises(AuthError):
            await AuthService(session).reset_password("expired-token", "brandnewpass1")
    assert expired_record.id is not None  # sanity: the row was actually created


@pytest.mark.asyncio
async def test_reset_password_revokes_other_sessions(client, session_factory):
    await client.post(
        "/api/auth/register",
        json={"email": "rprt@example.com", "full_name": "RPRT", "password": "supersecret1"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": "rprt@example.com", "password": "supersecret1"}
    )
    old_refresh_token = login.json()["refresh_token"]

    with patch("auth.service.logger") as mock_logger:
        async with session_factory() as session:
            await AuthService(session).request_password_reset("rprt@example.com")
        token = mock_logger.warning.call_args[0][3]

    reset = await client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "brandnewpass1"},
    )
    assert reset.status_code == 204

    refreshed = await client.post(
        "/api/auth/refresh", json={"refresh_token": old_refresh_token}
    )
    assert refreshed.status_code == 401

    new_login = await client.post(
        "/api/auth/login", json={"email": "rprt@example.com", "password": "brandnewpass1"}
    )
    assert new_login.status_code == 200
