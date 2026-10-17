"""Tests for scoped (read-only) access tokens — auth/scopes.py, ADR-0003."""

import importlib.util
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt as pyjwt
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from auth.jwt import (
    create_access_token,
    create_oauth_state_token,
    create_scoped_access_token,
    decode_access_claims,
    decode_access_token,
)
from auth.password import hash_password
from auth.scopes import READ_SCOPE
from models.log import LogEntry
from models.user import User, UserRole
from utils.config import get_settings


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _make_user(
    session_factory,
    *,
    email: str = "owner@example.com",
    role: UserRole = UserRole.ADMIN,
    is_active: bool = True,
) -> User:
    async with session_factory() as session:
        user = User(
            email=email,
            full_name="Owner",
            hashed_password=hash_password("testpass123"),
            role=role,
            is_active=is_active,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def owner(session_factory) -> User:
    return await _make_user(session_factory)


@pytest.fixture
def read_headers(owner) -> dict[str, str]:
    token = create_scoped_access_token(str(owner.id), READ_SCOPE, expires_days=30)
    return {"Authorization": f"Bearer {token}"}


def _headers_for(claims: dict) -> dict[str, str]:
    settings = get_settings()
    token = pyjwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


# --- token creation / decoding ---------------------------------------------


def test_scoped_token_carries_scope_jti_and_expiry(owner):
    token = create_scoped_access_token(str(owner.id), READ_SCOPE, expires_days=7)
    claims = decode_access_claims(token)

    assert claims is not None
    assert claims["sub"] == str(owner.id)
    assert claims["scope"] == READ_SCOPE
    assert claims["jti"]
    remaining = claims["exp"] - time.time()
    assert 6 * 86400 < remaining <= 7 * 86400


def test_each_scoped_token_has_a_unique_jti(owner):
    first = decode_access_claims(
        create_scoped_access_token(str(owner.id), READ_SCOPE, expires_days=1)
    )
    second = decode_access_claims(
        create_scoped_access_token(str(owner.id), READ_SCOPE, expires_days=1)
    )
    assert first["jti"] != second["jti"]


@pytest.mark.parametrize("days", [0, -1, 91])
def test_scoped_token_ttl_is_capped(owner, days):
    with pytest.raises(ValueError):
        create_scoped_access_token(str(owner.id), READ_SCOPE, expires_days=days)


def test_scoped_token_requires_a_scope(owner):
    with pytest.raises(ValueError):
        create_scoped_access_token(str(owner.id), "", expires_days=1)


def test_decode_access_token_rejects_scoped_tokens(owner):
    scoped = create_scoped_access_token(str(owner.id), READ_SCOPE, expires_days=1)
    assert decode_access_token(scoped) is None
    # ... while a normal access token still decodes to its subject.
    assert decode_access_token(create_access_token(str(owner.id))) == str(owner.id)


def test_oauth_state_tokens_are_not_access_tokens(owner):
    state = create_oauth_state_token(owner.id)
    assert decode_access_claims(state) is None
    assert decode_access_token(state) is None


# --- enforcement through the API -------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/agents",
        "/api/agents/tools",
        "/api/admin/status",
        "/api/admin/agents",
        "/api/admin/tools",
        "/api/admin/executions",
        "/api/admin/observation",
        "/api/goals",
        "/api/goals/ready",
        "/api/tasks",
    ],
)
async def test_read_scope_allows_allowlisted_get(client, read_headers, path):
    response = await client.get(path, headers=read_headers)
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/admin/users",
        "/api/admin/settings",
        "/api/admin/logs",
        "/api/admin/whatsapp",
        "/api/admin/memory",
        "/api/auth/me",
        "/api/contacts",
        "/api/messages",
        "/api/goals/1/history",
        "/api/goals/1/dependencies",
    ],
)
async def test_read_scope_blocks_everything_off_the_allowlist(
    client, read_headers, path
):
    response = await client.get(path, headers=read_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/agents/store/run"),
        ("POST", "/api/tasks"),
        ("POST", "/api/goals"),
        ("DELETE", "/api/tasks/1"),
        ("POST", "/api/admin/jobs/1/cancel"),
    ],
)
async def test_read_scope_blocks_real_write_routes(client, read_headers, method, path):
    # These routes exist and would act as the owner (run an agent, create or
    # delete data, cancel a job): the scope must stop them in the dependency,
    # before any handler runs.
    response = await client.request(method, path, headers=read_headers, json={})
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "path", ["/api/agents/store/run", "/api/tasks", "/api/goals", "/api/tasks/1"]
)
async def test_read_scope_never_succeeds_on_a_write_method(
    client, read_headers, method, path
):
    # Not every method/path pair is a route (the router answers 405 before
    # authentication for those); what must hold is that none ever succeeds.
    response = await client.request(method, path, headers=read_headers, json={})
    assert response.status_code in (403, 405)


@pytest.mark.asyncio
async def test_trailing_slash_does_not_bypass_the_allowlist(client, read_headers):
    allowed = await client.get("/api/admin/executions/", headers=read_headers)
    denied = await client.get("/api/admin/users/", headers=read_headers)
    assert allowed.status_code in (200, 307)
    assert denied.status_code in (403, 307)
    if denied.status_code == 307:
        # A redirect target is re-authorised on its own, never trusted.
        followed = await client.get(denied.headers["location"], headers=read_headers)
        assert followed.status_code == 403


@pytest.mark.asyncio
async def test_unknown_scope_gets_no_access(client, owner):
    token = create_scoped_access_token(str(owner.id), "darioos:write", expires_days=1)
    response = await client.get(
        "/api/agents", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_string_scope_gets_no_access(client, owner):
    now = datetime.now(timezone.utc)
    headers = _headers_for(
        {
            "sub": str(owner.id),
            "scope": ["darioos:read"],
            "iat": now,
            "exp": now + timedelta(days=1),
        }
    )
    assert (await client.get("/api/agents", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_full_access_tokens_are_unaffected(client, owner):
    headers = {"Authorization": f"Bearer {create_access_token(str(owner.id))}"}

    assert (await client.get("/api/admin/users", headers=headers)).status_code == 200
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_oauth_state_token_cannot_be_used_as_bearer(client, owner):
    token = create_oauth_state_token(owner.id)
    response = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


# --- lifecycle: expiry, revocation, deactivation ----------------------------


@pytest.mark.asyncio
async def test_expired_scoped_token_is_rejected(client, owner):
    now = datetime.now(timezone.utc)
    headers = _headers_for(
        {
            "sub": str(owner.id),
            "scope": READ_SCOPE,
            "jti": "x",
            "iat": now - timedelta(days=2),
            "exp": now - timedelta(days=1),
        }
    )
    assert (await client.get("/api/agents", headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_revoked_before_rejects_older_scoped_tokens(
    client, read_headers, monkeypatch
):
    settings = get_settings()
    assert (await client.get("/api/agents", headers=read_headers)).status_code == 200

    monkeypatch.setattr(settings, "scoped_token_revoked_before", int(time.time()) + 60)
    assert (await client.get("/api/agents", headers=read_headers)).status_code == 401


@pytest.mark.asyncio
async def test_revoked_before_does_not_touch_full_access_tokens(
    client, owner, monkeypatch
):
    monkeypatch.setattr(
        get_settings(), "scoped_token_revoked_before", int(time.time()) + 60
    )
    headers = {"Authorization": f"Bearer {create_access_token(str(owner.id))}"}
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_scoped_token_of_an_inactive_user_is_rejected(client, session_factory):
    user = await _make_user(
        session_factory, email="inactive@example.com", is_active=False
    )
    token = create_scoped_access_token(str(user.id), READ_SCOPE, expires_days=1)
    response = await client.get(
        "/api/agents", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_scoped_token_with_malformed_subject_is_rejected(client):
    now = datetime.now(timezone.utc)
    headers = _headers_for(
        {
            "sub": "not-a-number",
            "scope": READ_SCOPE,
            "iat": now,
            "exp": now + timedelta(days=1),
        }
    )
    assert (await client.get("/api/agents", headers=headers)).status_code == 401


# --- scripts/mint_scoped_token.py -------------------------------------------


def _load_mint_script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "mint_scoped_token.py"
    spec = importlib.util.spec_from_file_location("mint_scoped_token", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_mint_script_issues_a_working_audited_token(
    client, owner, session_factory, monkeypatch
):
    mint_script = _load_mint_script()
    monkeypatch.setattr(mint_script, "async_session_factory", session_factory)

    token = await mint_script.mint(owner.email, days=14, scope=READ_SCOPE)

    response = await client.get(
        "/api/agents", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    async with session_factory() as session:
        entries = (
            (
                await session.execute(
                    select(LogEntry).where(LogEntry.source == "auth:scoped_token")
                )
            )
            .scalars()
            .all()
        )
    assert len(entries) == 1
    audit = entries[0].payload
    assert audit["user_id"] == owner.id
    assert audit["scope"] == READ_SCOPE
    assert audit["expires_days"] == 14
    assert audit["jti"] == decode_access_claims(token)["jti"]
    # The credential itself must never reach the log.
    assert token not in str(audit)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup",
    [
        pytest.param({"role": UserRole.USER}, id="non-admin"),
        pytest.param({"is_active": False}, id="inactive"),
    ],
)
async def test_mint_script_refuses_non_owner_accounts(
    session_factory, monkeypatch, setup
):
    user = await _make_user(session_factory, email="other@example.com", **setup)
    mint_script = _load_mint_script()
    monkeypatch.setattr(mint_script, "async_session_factory", session_factory)

    with pytest.raises(SystemExit):
        await mint_script.mint(user.email, days=1, scope=READ_SCOPE)


@pytest.mark.asyncio
async def test_mint_script_refuses_unknown_email(session_factory, monkeypatch):
    mint_script = _load_mint_script()
    monkeypatch.setattr(mint_script, "async_session_factory", session_factory)

    with pytest.raises(SystemExit):
        await mint_script.mint("nobody@example.com", days=1, scope=READ_SCOPE)
