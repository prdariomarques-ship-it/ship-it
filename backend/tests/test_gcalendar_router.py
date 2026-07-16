"""OAuth connect/callback/status/disconnect endpoints (Sprint 2 — Google
Calendar). Mirrors `tests/test_mail_router.py`, with the Sprint 1.1 findings
(XSS escaping, race-safe upsert) tested from the start instead of as a
follow-up.
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
from models.gcalendar_account import GoogleCalendarAccount
from providers.calendar.base import CalendarProviderError, OAuthTokens
from providers.calendar.factory import get_calendar_provider
from repositories.gcalendar_account import GoogleCalendarAccountRepository
from utils.config import get_settings

_PURPOSE = "gcalendar_oauth_state"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    get_calendar_provider.cache_clear()
    monkeypatch.setattr(get_settings(), "google_client_id", "client-id")
    monkeypatch.setattr(get_settings(), "google_client_secret", "client-secret")
    monkeypatch.setattr(
        get_settings(),
        "google_calendar_redirect_uri",
        "https://app.example.com/api/gcalendar/oauth/callback",
    )
    monkeypatch.setattr(
        get_settings(), "email_token_encryption_key", Fernet.generate_key().decode()
    )
    yield
    get_calendar_provider.cache_clear()


@pytest.fixture(autouse=True)
def _no_real_network_for_label_lookup():
    with patch(
        "gcalendar.router._resolve_account_label", new=AsyncMock(return_value="Dario")
    ):
        yield


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def second_user_headers(client, auth_headers):
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
    name = "google"

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
    response = await client.get("/api/gcalendar/connect", headers=auth_headers)
    assert response.status_code == 200
    url = response.json()["authorization_url"]
    state = url.split("state=")[1]
    assert decode_oauth_state_token(state, purpose=_PURPOSE) is not None


@pytest.mark.asyncio
async def test_connect_forbidden_for_non_admin(client, second_user_headers):
    response = await client.get("/api/gcalendar/connect", headers=second_user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_connect_requires_authentication(client):
    response = await client.get("/api/gcalendar/connect")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_connect_unconfigured_returns_503(client, auth_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_calendar_redirect_uri", "")
    response = await client.get("/api/gcalendar/connect", headers=auth_headers)
    assert response.status_code == 503


# --- /oauth/callback -------------------------------------------------------------
@pytest.mark.asyncio
async def test_callback_missing_code_or_state_fails_cleanly(client):
    response = await client.get("/api/gcalendar/oauth/callback")
    assert response.status_code == 200
    assert "Falha" in response.text


@pytest.mark.asyncio
async def test_callback_escapes_the_error_param_against_reflected_xss(client):
    payload = "<script>alert(document.cookie)</script>"
    response = await client.get(
        "/api/gcalendar/oauth/callback", params={"error": payload}
    )
    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


@pytest.mark.asyncio
async def test_callback_rejects_invalid_state(client):
    response = await client.get(
        "/api/gcalendar/oauth/callback",
        params={"code": "abc", "state": "not-a-real-token"},
    )
    assert response.status_code == 200
    assert "expirada" in response.text or "inválida" in response.text


@pytest.mark.asyncio
async def test_callback_rejects_a_gmail_state_token(client):
    """A state token minted for the Gmail callback must not be accepted
    here — each domain's OAuth round-trip is isolated even though all three
    share the same `create_oauth_state_token`/`decode_oauth_state_token`
    helper."""
    gmail_state = create_oauth_state_token(1, purpose="gmail_oauth_state")
    response = await client.get(
        "/api/gcalendar/oauth/callback", params={"code": "abc", "state": gmail_state}
    )
    assert response.status_code == 200
    assert "Falha" in response.text or "inválida" in response.text


@pytest.mark.asyncio
async def test_callback_rejects_a_state_token_of_the_wrong_purpose(client):
    not_a_state_token = create_access_token(subject="1")
    response = await client.get(
        "/api/gcalendar/oauth/callback",
        params={"code": "abc", "state": not_a_state_token},
    )
    assert response.status_code == 200
    assert "Falha" in response.text or "inválida" in response.text


@pytest.mark.asyncio
async def test_callback_success_stores_an_encrypted_refresh_token(
    client, auth_headers, db_engine
):
    me = await client.get("/api/auth/me", headers=auth_headers)
    user_id = me.json()["id"]
    state = create_oauth_state_token(user_id, purpose=_PURPOSE)
    tokens = OAuthTokens(
        access_token="at",
        refresh_token="rt-plaintext",
        expires_in=3600,
        scope="calendar",
    )

    with patch(
        "gcalendar.router.get_calendar_provider",
        return_value=_FakeProvider(tokens=tokens),
    ):
        response = await client.get(
            "/api/gcalendar/oauth/callback", params={"code": "abc", "state": state}
        )

    assert response.status_code == 200
    assert "sucesso" in response.text

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        account = (await session.execute(select(GoogleCalendarAccount))).scalar_one()
    assert account.user_id == user_id
    assert account.account_label == "Dario"
    assert account.encrypted_refresh_token != "rt-plaintext"


@pytest.mark.asyncio
async def test_callback_reconnect_updates_the_existing_account_instead_of_duplicating(
    client, auth_headers, db_engine
):
    me = await client.get("/api/auth/me", headers=auth_headers)
    user_id = me.json()["id"]
    first_tokens = OAuthTokens(
        access_token="at1", refresh_token="rt1", scope="calendar"
    )
    second_tokens = OAuthTokens(
        access_token="at2", refresh_token="rt2", scope="calendar"
    )

    with patch(
        "gcalendar.router.get_calendar_provider",
        return_value=_FakeProvider(tokens=first_tokens),
    ):
        state = create_oauth_state_token(user_id, purpose=_PURPOSE)
        await client.get(
            "/api/gcalendar/oauth/callback", params={"code": "abc", "state": state}
        )
    with patch(
        "gcalendar.router.get_calendar_provider",
        return_value=_FakeProvider(tokens=second_tokens),
    ):
        state2 = create_oauth_state_token(user_id, purpose=_PURPOSE)
        await client.get(
            "/api/gcalendar/oauth/callback", params={"code": "abc2", "state": state2}
        )

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        accounts = (
            (await session.execute(select(GoogleCalendarAccount))).scalars().all()
        )
    assert len(accounts) == 1


@pytest.mark.asyncio
async def test_callback_recovers_when_two_concurrent_callbacks_race_on_create(
    client, auth_headers, session_factory, db_engine, monkeypatch
):
    me = await client.get("/api/auth/me", headers=auth_headers)
    user_id = me.json()["id"]

    original_get_by_user = GoogleCalendarAccountRepository.get_by_user
    calls = {"count": 0}

    async def racy_get_by_user(self, uid, provider):
        calls["count"] += 1
        if calls["count"] <= 2:
            return None
        return await original_get_by_user(self, uid, provider)

    monkeypatch.setattr(
        GoogleCalendarAccountRepository, "get_by_user", racy_get_by_user
    )

    async with session_factory() as session:
        first = await GoogleCalendarAccountRepository(session).upsert_for_user(
            user_id,
            "google",
            account_label="racer",
            encrypted_refresh_token="enc-1",
            scopes=["calendar"],
            connected_at=datetime.now(timezone.utc),
        )
    async with session_factory() as session:
        second = await GoogleCalendarAccountRepository(session).upsert_for_user(
            user_id,
            "google",
            account_label="racer",
            encrypted_refresh_token="enc-2",
            scopes=["calendar"],
            connected_at=datetime.now(timezone.utc),
        )
    assert first.id == second.id
    assert calls["count"] == 3

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        rows = (await session.execute(select(GoogleCalendarAccount))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_callback_without_a_refresh_token_fails_and_stores_nothing(
    client, auth_headers, db_engine
):
    me = await client.get("/api/auth/me", headers=auth_headers)
    state = create_oauth_state_token(me.json()["id"], purpose=_PURPOSE)
    tokens = OAuthTokens(access_token="at", refresh_token=None, scope="calendar")

    with patch(
        "gcalendar.router.get_calendar_provider",
        return_value=_FakeProvider(tokens=tokens),
    ):
        response = await client.get(
            "/api/gcalendar/oauth/callback", params={"code": "abc", "state": state}
        )
    assert "refresh token" in response.text.lower() or "Falha" in response.text

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        accounts = (
            (await session.execute(select(GoogleCalendarAccount))).scalars().all()
        )
    assert accounts == []


@pytest.mark.asyncio
async def test_callback_without_encryption_configured_fails_and_stores_nothing(
    client, auth_headers, db_engine, monkeypatch
):
    monkeypatch.setattr(get_settings(), "email_token_encryption_key", "")
    state = create_oauth_state_token(
        (await client.get("/api/auth/me", headers=auth_headers)).json()["id"],
        purpose=_PURPOSE,
    )
    tokens = OAuthTokens(access_token="at", refresh_token="rt", scope="calendar")

    with patch(
        "gcalendar.router.get_calendar_provider",
        return_value=_FakeProvider(tokens=tokens),
    ):
        response = await client.get(
            "/api/gcalendar/oauth/callback", params={"code": "abc", "state": state}
        )
    assert "Falha" in response.text

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        accounts = (
            (await session.execute(select(GoogleCalendarAccount))).scalars().all()
        )
    assert accounts == []


@pytest.mark.asyncio
async def test_callback_google_token_exchange_failure_fails_cleanly(
    client, auth_headers
):
    state = create_oauth_state_token(
        (await client.get("/api/auth/me", headers=auth_headers)).json()["id"],
        purpose=_PURPOSE,
    )
    with patch(
        "gcalendar.router.get_calendar_provider",
        return_value=_FakeProvider(exc=CalendarProviderError("boom")),
    ):
        response = await client.get(
            "/api/gcalendar/oauth/callback", params={"code": "abc", "state": state}
        )
    assert response.status_code == 200
    assert "Falha" in response.text


# --- /status and /disconnect -----------------------------------------------------
@pytest.mark.asyncio
async def test_status_reports_not_connected_by_default(client, auth_headers):
    response = await client.get("/api/gcalendar/status", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {
        "connected": False,
        "account_label": None,
        "connected_at": None,
    }


@pytest.mark.asyncio
async def test_status_forbidden_for_non_admin(client, second_user_headers):
    response = await client.get("/api/gcalendar/status", headers=second_user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_status_and_disconnect_reflect_a_connected_account(
    client, auth_headers, db_engine
):
    state = create_oauth_state_token(
        (await client.get("/api/auth/me", headers=auth_headers)).json()["id"],
        purpose=_PURPOSE,
    )
    tokens = OAuthTokens(access_token="at", refresh_token="rt", scope="calendar")
    with patch(
        "gcalendar.router.get_calendar_provider",
        return_value=_FakeProvider(tokens=tokens),
    ):
        await client.get(
            "/api/gcalendar/oauth/callback", params={"code": "abc", "state": state}
        )

    status_response = await client.get("/api/gcalendar/status", headers=auth_headers)
    assert status_response.json()["connected"] is True

    disconnect_response = await client.delete(
        "/api/gcalendar/disconnect", headers=auth_headers
    )
    assert disconnect_response.status_code == 204

    status_after = await client.get("/api/gcalendar/status", headers=auth_headers)
    assert status_after.json()["connected"] is False


@pytest.mark.asyncio
async def test_disconnect_forbidden_for_non_admin(client, second_user_headers):
    response = await client.delete(
        "/api/gcalendar/disconnect", headers=second_user_headers
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_disconnect_is_a_no_op_when_nothing_is_connected(client, auth_headers):
    response = await client.delete("/api/gcalendar/disconnect", headers=auth_headers)
    assert response.status_code == 204
