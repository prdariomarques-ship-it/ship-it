"""OAuth connect/callback/status/disconnect endpoints (Sprint 1 — Gmail).

`/connect`, `/status` and `/disconnect` are admin-only (dashboard setup, not a
chat surface); `/oauth/callback` is the one route Google itself calls, so it
is authenticated differently — via the short-lived signed `state` token
minted by `/connect` (see `auth/jwt.py::create_oauth_state_token`).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from auth.jwt import (
    create_access_token,
    create_oauth_state_token,
    decode_oauth_state_token,
)
from models.email_account import EmailAccount
from providers.mail.base import MailProviderError, OAuthTokens
from providers.mail.factory import get_mail_provider
from repositories.email_account import EmailAccountRepository
from utils.config import get_settings


@pytest.fixture(autouse=True)
def _configured_mail(monkeypatch):
    # get_mail_provider() is lru_cache'd: without clearing it, a provider
    # instance constructed by an earlier test (with different settings) can
    # leak into this file's tests regardless of the monkeypatches below.
    get_mail_provider.cache_clear()
    monkeypatch.setattr(get_settings(), "google_client_id", "client-id")
    monkeypatch.setattr(get_settings(), "google_client_secret", "client-secret")
    monkeypatch.setattr(
        get_settings(),
        "google_redirect_uri",
        "https://app.example.com/api/mail/oauth/callback",
    )
    monkeypatch.setattr(
        get_settings(), "email_token_encryption_key", Fernet.generate_key().decode()
    )
    yield
    get_mail_provider.cache_clear()


@pytest.fixture(autouse=True)
def _no_real_network_for_profile_lookup():
    with patch(
        "mail.router._resolve_email_address",
        new=AsyncMock(return_value="dario@gmail.com"),
    ):
        yield


@pytest.fixture
async def second_user_headers(client, auth_headers):
    """Depends on `auth_headers` so the admin account always registers
    first — only the very first account in the database bootstraps as
    admin, and this fixture must reliably land as a plain USER."""
    await client.post(
        "/api/auth/register",
        json={
            "email": "second@example.com",
            "full_name": "Second",
            "password": "supersecret1",
        },
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": "second@example.com", "password": "supersecret1"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class _FakeProvider:
    name = "gmail"

    def __init__(self, tokens=None, exc=None):
        self._tokens = tokens
        self._exc = exc

    def authorization_url(self, state: str) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"

    async def exchange_code(self, code: str) -> OAuthTokens:
        if self._exc:
            raise self._exc
        return self._tokens


# --- /connect ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_connect_returns_authorization_url_with_a_valid_state_token(
    client, auth_headers
):
    response = await client.get("/api/mail/connect", headers=auth_headers)
    assert response.status_code == 200
    url = response.json()["authorization_url"]
    assert "accounts.google.com" in url
    state = url.split("state=")[1]
    assert decode_oauth_state_token(state) is not None


@pytest.mark.asyncio
async def test_connect_forbidden_for_non_admin(
    client, auth_headers, second_user_headers
):
    response = await client.get("/api/mail/connect", headers=second_user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_connect_requires_authentication(client):
    response = await client.get("/api/mail/connect")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_connect_unconfigured_returns_503(client, auth_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "")
    response = await client.get("/api/mail/connect", headers=auth_headers)
    assert response.status_code == 503


# --- /oauth/callback -------------------------------------------------------------
@pytest.mark.asyncio
async def test_callback_missing_code_or_state_fails_cleanly(client):
    response = await client.get("/api/mail/oauth/callback")
    assert response.status_code == 200
    assert "Falha" in response.text


@pytest.mark.asyncio
async def test_callback_surfaces_google_error_param(client):
    response = await client.get(
        "/api/mail/oauth/callback", params={"error": "access_denied"}
    )
    assert response.status_code == 200
    assert "recusou" in response.text


@pytest.mark.asyncio
async def test_callback_escapes_the_error_param_against_reflected_xss(client):
    """`error` is an unauthenticated, attacker-controllable query param
    (Google's own callback contract) reflected straight into the HTML
    response — it must never reach the page unescaped."""
    payload = "<script>alert(document.cookie)</script>"
    response = await client.get("/api/mail/oauth/callback", params={"error": payload})
    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


@pytest.mark.asyncio
async def test_callback_rejects_invalid_state(client):
    response = await client.get(
        "/api/mail/oauth/callback", params={"code": "abc", "state": "not-a-real-token"}
    )
    assert response.status_code == 200
    assert "expirada" in response.text or "inválida" in response.text


@pytest.mark.asyncio
async def test_callback_rejects_a_state_token_of_the_wrong_purpose(client):
    """A normal access token must not be accepted as an OAuth state — the
    purpose claim is checked, not just the signature."""
    not_a_state_token = create_access_token(subject="1")
    response = await client.get(
        "/api/mail/oauth/callback", params={"code": "abc", "state": not_a_state_token}
    )
    assert response.status_code == 200
    assert "Falha" in response.text or "inválida" in response.text


@pytest.mark.asyncio
async def test_callback_success_stores_an_encrypted_refresh_token(
    client, auth_headers, db_engine
):
    me = await client.get("/api/auth/me", headers=auth_headers)
    user_id = me.json()["id"]
    state = create_oauth_state_token(user_id)
    tokens = OAuthTokens(
        access_token="at",
        refresh_token="rt-plaintext",
        expires_in=3600,
        scope="gmail.readonly",
    )

    with patch(
        "mail.router.get_mail_provider", return_value=_FakeProvider(tokens=tokens)
    ):
        response = await client.get(
            "/api/mail/oauth/callback", params={"code": "abc", "state": state}
        )

    assert response.status_code == 200
    assert "sucesso" in response.text

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        account = (await session.execute(select(EmailAccount))).scalar_one()
    assert account.user_id == user_id
    assert account.email_address == "dario@gmail.com"
    assert (
        account.encrypted_refresh_token != "rt-plaintext"
    )  # never stored in plaintext


@pytest.mark.asyncio
async def test_callback_reconnect_updates_the_existing_account_instead_of_duplicating(
    client, auth_headers, db_engine
):
    me = await client.get("/api/auth/me", headers=auth_headers)
    user_id = me.json()["id"]
    state = create_oauth_state_token(user_id)
    first_tokens = OAuthTokens(
        access_token="at1", refresh_token="rt1", scope="gmail.readonly"
    )
    second_tokens = OAuthTokens(
        access_token="at2", refresh_token="rt2", scope="gmail.readonly"
    )

    with patch(
        "mail.router.get_mail_provider", return_value=_FakeProvider(tokens=first_tokens)
    ):
        await client.get(
            "/api/mail/oauth/callback", params={"code": "abc", "state": state}
        )
    state2 = create_oauth_state_token(user_id)
    with patch(
        "mail.router.get_mail_provider",
        return_value=_FakeProvider(tokens=second_tokens),
    ):
        await client.get(
            "/api/mail/oauth/callback", params={"code": "abc2", "state": state2}
        )

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        accounts = (await session.execute(select(EmailAccount))).scalars().all()
    assert len(accounts) == 1


@pytest.mark.asyncio
async def test_callback_recovers_when_two_concurrent_callbacks_race_on_create(
    client, auth_headers, session_factory, db_engine, monkeypatch
):
    """Two concurrent OAuth callbacks completing for the same user (e.g. two
    browser tabs) both check for an existing EmailAccount before either has
    committed, so both see "not connected yet" and both attempt to create
    one — the second must actually hit the real UNIQUE(user_id, provider)
    constraint and recover via `EmailAccountRepository.upsert_for_user`'s
    IntegrityError branch, not crash. (An earlier version of this test only
    exercised the ordinary reconnect/update path — confirmed by coverage
    showing the except-IntegrityError branch never ran — this one forces the
    real race: both initial lookups return None, only the retry lookup
    inside the except block sees the row the other task already committed.)
    """
    me = await client.get("/api/auth/me", headers=auth_headers)
    user_id = me.json()["id"]

    original_get_by_user = EmailAccountRepository.get_by_user
    calls = {"count": 0}

    async def racy_get_by_user(self, uid, provider):
        calls["count"] += 1
        if calls["count"] <= 2:
            # Both tasks' initial check races before either commits.
            return None
        return await original_get_by_user(self, uid, provider)

    monkeypatch.setattr(EmailAccountRepository, "get_by_user", racy_get_by_user)

    async with session_factory() as session:
        first = await EmailAccountRepository(session).upsert_for_user(
            user_id,
            "gmail",
            email_address="racer@gmail.com",
            encrypted_refresh_token="enc-1",
            scopes=["gmail.readonly"],
            connected_at=datetime.now(timezone.utc),
        )
    async with session_factory() as session:
        second = await EmailAccountRepository(session).upsert_for_user(
            user_id,
            "gmail",
            email_address="racer@gmail.com",
            encrypted_refresh_token="enc-2",
            scopes=["gmail.readonly"],
            connected_at=datetime.now(timezone.utc),
        )
    assert calls["count"] == 3  # both initial checks (racing) + one recovery re-fetch

    assert first.id == second.id  # same row, not a duplicate

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        rows = (await session.execute(select(EmailAccount))).scalars().all()
    assert len(rows) == 1


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_callback_without_a_refresh_token_fails_and_stores_nothing(
    client, auth_headers, db_engine
):
    me = await client.get("/api/auth/me", headers=auth_headers)
    state = create_oauth_state_token(me.json()["id"])
    tokens = OAuthTokens(access_token="at", refresh_token=None, scope="gmail.readonly")

    with patch(
        "mail.router.get_mail_provider", return_value=_FakeProvider(tokens=tokens)
    ):
        response = await client.get(
            "/api/mail/oauth/callback", params={"code": "abc", "state": state}
        )
    assert "refresh token" in response.text.lower() or "Falha" in response.text

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        accounts = (await session.execute(select(EmailAccount))).scalars().all()
    assert accounts == []


@pytest.mark.asyncio
async def test_callback_without_encryption_configured_fails_and_stores_nothing(
    client, auth_headers, db_engine, monkeypatch
):
    monkeypatch.setattr(get_settings(), "email_token_encryption_key", "")
    me = await client.get("/api/auth/me", headers=auth_headers)
    state = create_oauth_state_token(me.json()["id"])
    tokens = OAuthTokens(access_token="at", refresh_token="rt", scope="gmail.readonly")

    with patch(
        "mail.router.get_mail_provider", return_value=_FakeProvider(tokens=tokens)
    ):
        response = await client.get(
            "/api/mail/oauth/callback", params={"code": "abc", "state": state}
        )
    assert "Falha" in response.text

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        accounts = (await session.execute(select(EmailAccount))).scalars().all()
    assert accounts == []


@pytest.mark.asyncio
async def test_callback_google_token_exchange_failure_fails_cleanly(
    client, auth_headers
):
    me = await client.get("/api/auth/me", headers=auth_headers)
    state = create_oauth_state_token(me.json()["id"])

    with patch(
        "mail.router.get_mail_provider",
        return_value=_FakeProvider(exc=MailProviderError("boom")),
    ):
        response = await client.get(
            "/api/mail/oauth/callback", params={"code": "abc", "state": state}
        )
    assert response.status_code == 200
    assert "Falha" in response.text


# --- /status and /disconnect -----------------------------------------------------
@pytest.mark.asyncio
async def test_status_reports_not_connected_by_default(client, auth_headers):
    response = await client.get("/api/mail/status", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {
        "connected": False,
        "email_address": None,
        "connected_at": None,
    }


@pytest.mark.asyncio
async def test_status_forbidden_for_non_admin(client, second_user_headers):
    response = await client.get("/api/mail/status", headers=second_user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_status_and_disconnect_reflect_a_connected_account(
    client, auth_headers, db_engine
):
    me = await client.get("/api/auth/me", headers=auth_headers)
    state = create_oauth_state_token(me.json()["id"])
    tokens = OAuthTokens(access_token="at", refresh_token="rt", scope="gmail.readonly")
    with patch(
        "mail.router.get_mail_provider", return_value=_FakeProvider(tokens=tokens)
    ):
        await client.get(
            "/api/mail/oauth/callback", params={"code": "abc", "state": state}
        )

    status_response = await client.get("/api/mail/status", headers=auth_headers)
    assert status_response.json()["connected"] is True
    assert status_response.json()["email_address"] == "dario@gmail.com"

    disconnect_response = await client.delete(
        "/api/mail/disconnect", headers=auth_headers
    )
    assert disconnect_response.status_code == 204

    status_after = await client.get("/api/mail/status", headers=auth_headers)
    assert status_after.json()["connected"] is False


@pytest.mark.asyncio
async def test_disconnect_forbidden_for_non_admin(client, second_user_headers):
    response = await client.delete("/api/mail/disconnect", headers=second_user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_disconnect_is_a_no_op_when_nothing_is_connected(client, auth_headers):
    response = await client.delete("/api/mail/disconnect", headers=auth_headers)
    assert response.status_code == 204
