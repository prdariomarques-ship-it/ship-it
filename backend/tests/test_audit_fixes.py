"""Regression tests for the Phase-2 audit fixes."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from main import _validate_production_settings
from models.job import Job
from repositories.contact import ContactRepository
from services.rate_limit import RateLimiter, rate_limiter
from utils.config import get_settings


# --- Production settings guard ---------------------------------------------
def test_production_requires_strong_jwt_secret():
    weak = SimpleNamespace(environment="production", jwt_secret="change-me-in-production")
    with pytest.raises(RuntimeError):
        _validate_production_settings(weak)

    short = SimpleNamespace(environment="production", jwt_secret="short")
    with pytest.raises(RuntimeError):
        _validate_production_settings(short)

    strong = SimpleNamespace(environment="production", jwt_secret="x" * 64, webhook_secret="y" * 32)
    _validate_production_settings(strong)  # must not raise

    dev = SimpleNamespace(environment="development", jwt_secret="change-me-in-production")
    _validate_production_settings(dev)  # dev keeps working with the default


# --- PROD-004: production requires a strong WEBHOOK_SECRET ------------------
def test_development_does_not_require_a_webhook_secret():
    """Dev environment: no WEBHOOK_SECRET at all must not block boot."""
    dev = SimpleNamespace(environment="development", jwt_secret="x" * 64, webhook_secret="")
    _validate_production_settings(dev)  # must not raise


def test_production_rejects_missing_webhook_secret():
    """Prod environment, secret ausente."""
    missing = SimpleNamespace(environment="production", jwt_secret="x" * 64, webhook_secret="")
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        _validate_production_settings(missing)


def test_production_rejects_weak_webhook_secret():
    """Prod environment, secret inválido (curto demais)."""
    weak = SimpleNamespace(environment="production", jwt_secret="x" * 64, webhook_secret="short")
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        _validate_production_settings(weak)


def test_production_accepts_strong_webhook_secret():
    """Prod environment, secret válido."""
    strong = SimpleNamespace(environment="production", jwt_secret="x" * 64, webhook_secret="z" * 32)
    _validate_production_settings(strong)  # must not raise


def test_production_still_checks_jwt_secret_before_webhook_secret():
    """A weak JWT_SECRET is caught even with a strong WEBHOOK_SECRET present —
    the two checks are independent, neither masks the other."""
    both_set_but_jwt_weak = SimpleNamespace(
        environment="production", jwt_secret="short", webhook_secret="z" * 32
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _validate_production_settings(both_set_but_jwt_weak)


# --- Webhook authentication --------------------------------------------------
@pytest.mark.asyncio
async def test_webhook_rejects_missing_or_wrong_token_when_secret_set(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "webhook_secret", "super-secret")

    payload = {"from": "5511900000001@c.us", "body": "oi", "notifyName": "X"}
    missing = await client.post("/api/webhooks/whatsapp", json=payload)
    assert missing.status_code == 401

    wrong = await client.post(
        "/api/webhooks/whatsapp", json=payload, headers={"X-Webhook-Token": "nope"}
    )
    assert wrong.status_code == 401

    right = await client.post(
        "/api/webhooks/whatsapp", json=payload, headers={"X-Webhook-Token": "super-secret"}
    )
    assert right.status_code == 200


@pytest.mark.asyncio
async def test_webhook_open_when_secret_not_configured(client):
    response = await client.post(
        "/api/webhooks/whatsapp",
        json={"from": "5511900000002@c.us", "body": "oi", "notifyName": "Y"},
    )
    assert response.status_code == 200


# --- Embedding moved off the hot path ----------------------------------------
@pytest.mark.asyncio
async def test_webhook_enqueues_embedding_job(client, db_engine):
    await client.post(
        "/api/webhooks/whatsapp",
        json={"from": "5511900000003@c.us", "body": "lembre disso", "notifyName": "Z"},
    )
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        jobs = (await session.execute(select(Job))).scalars().all()
    names = {job.name for job in jobs}
    assert "memory.embed" in names
    embed_job = next(job for job in jobs if job.name == "memory.embed")
    assert embed_job.payload["content"] == "lembre disso"


# --- Outbound messages also feed the automatic summary -----------------------
@pytest.mark.asyncio
async def test_outbound_send_triggers_summary_job(client, auth_headers, db_engine, monkeypatch):
    monkeypatch.setattr(get_settings(), "contact_summary_every_n_messages", 1)

    with patch(
        "providers.whatsapp.openwa.provider.OpenWAProvider.send_text",
        new=AsyncMock(return_value={"status": "ok"}),
    ):
        response = await client.post(
            "/api/whatsapp/send-text",
            json={"to": "5511900000004", "content": "olá!"},
            headers=auth_headers,
        )
    assert response.status_code == 200

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        jobs = (await session.execute(select(Job))).scalars().all()
    assert "contact.summarize" in {job.name for job in jobs}


# --- Contact creation race ----------------------------------------------------
@pytest.mark.asyncio
async def test_get_or_create_by_phone_recovers_from_unique_race(db_engine, monkeypatch):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async with factory() as session:
        existing = await ContactRepository(session).create(name="Ana", phone="5511911110000")

    # Simulate the race: the first lookup misses, the insert then collides with
    # a row committed by a concurrent request.
    original = ContactRepository.get_by_phone
    calls = {"count": 0}

    async def flaky_get_by_phone(self, phone):
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return await original(self, phone)

    monkeypatch.setattr(ContactRepository, "get_by_phone", flaky_get_by_phone)

    async with factory() as session:
        contact = await ContactRepository(session).get_or_create_by_phone("5511911110000")
    assert contact.id == existing.id
    assert calls["count"] == 2


# --- Rate limiting -------------------------------------------------------------
@pytest.mark.asyncio
async def test_rate_limiter_in_memory_window():
    limiter = RateLimiter()
    limiter._redis_available = False
    limiter._settings = SimpleNamespace(rate_limit_requests=2, rate_limit_window_seconds=60)

    assert await limiter.is_allowed("ip-1")
    assert await limiter.is_allowed("ip-1")
    assert not await limiter.is_allowed("ip-1")
    assert await limiter.is_allowed("ip-2")  # independent identifier


@pytest.mark.asyncio
async def test_health_and_metrics_exempt_from_rate_limit(client, monkeypatch):
    monkeypatch.setattr(rate_limiter, "is_allowed", AsyncMock(return_value=False))

    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/metrics")).status_code == 200
    throttled = await client.get("/api/agents")
    assert throttled.status_code == 429


# --- Refresh token hygiene ------------------------------------------------------
@pytest.mark.asyncio
async def test_login_purges_expired_refresh_tokens(client, db_engine):
    from datetime import datetime, timedelta, timezone

    from models.refresh_token import RefreshToken

    await client.post(
        "/api/auth/register",
        json={"email": "purge@example.com", "full_name": "P", "password": "supersecret1"},
    )
    await client.post(
        "/api/auth/login", json={"email": "purge@example.com", "password": "supersecret1"}
    )

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        tokens = (await session.execute(select(RefreshToken))).scalars().all()
        assert len(tokens) == 1
        tokens[0].expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        await session.commit()

    await client.post(
        "/api/auth/login", json={"email": "purge@example.com", "password": "supersecret1"}
    )
    async with factory() as session:
        tokens = (await session.execute(select(RefreshToken))).scalars().all()
    assert len(tokens) == 1  # the expired one is gone; only the new pair's token remains


# --- Contact search uses SQL, with partial matching ----------------------------
@pytest.mark.asyncio
async def test_contact_search_by_name_partial_case_insensitive(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        repository = ContactRepository(session)
        await repository.create(name="Maria Aparecida", phone="5511922220001")
        await repository.create(name="João Pedro", phone="5511922220002")

        matches = await repository.search_by_name("aparecida")
        assert [contact.name for contact in matches] == ["Maria Aparecida"]
