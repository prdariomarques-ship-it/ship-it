"""Webhook security: signature verification and duplicate-message protection."""
import hashlib
import hmac

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.message import Message
from providers.whatsapp.official.provider import OfficialProvider
from utils.config import get_settings

_OFFICIAL_PAYLOAD = {
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "contacts": [{"profile": {"name": "Sig"}, "wa_id": "5511900000099"}],
                        "messages": [
                            {
                                "from": "5511900000099",
                                "id": "wamid.SIG1",
                                "type": "text",
                                "text": {"body": "oi"},
                            }
                        ],
                    }
                }
            ]
        }
    ]
}


# --- Signature verification (unit-level, on the provider itself) ------------
def test_official_signature_verification_accepts_correct_hmac():
    provider = OfficialProvider()
    provider._app_secret = "app-secret-123"
    body = b'{"hello":"world"}'
    signature = "sha256=" + hmac.new(b"app-secret-123", body, hashlib.sha256).hexdigest()
    assert provider.verify_signature(body, {"x-hub-signature-256": signature})


def test_official_signature_verification_rejects_wrong_hmac():
    provider = OfficialProvider()
    provider._app_secret = "app-secret-123"
    body = b'{"hello":"world"}'
    assert not provider.verify_signature(body, {"x-hub-signature-256": "sha256=deadbeef"})


def test_official_signature_verification_rejects_missing_header():
    provider = OfficialProvider()
    provider._app_secret = "app-secret-123"
    assert not provider.verify_signature(b"{}", {})


def test_official_signature_verification_skipped_when_not_configured():
    provider = OfficialProvider()
    provider._app_secret = ""
    assert provider.verify_signature(b"anything", {})  # no secret configured -> no-op


def test_base_provider_default_signature_is_a_noop():
    from providers.whatsapp.openwa.provider import OpenWAProvider

    assert OpenWAProvider().verify_signature(b"anything", {})


# --- End-to-end signature verification through the webhook route ------------
@pytest.mark.asyncio
async def test_webhook_enforces_official_signature_when_configured(client, monkeypatch):
    from providers.whatsapp import factory as wa_factory

    monkeypatch.setattr(get_settings(), "whatsapp_provider", "official")
    monkeypatch.setattr(get_settings(), "official_app_secret", "top-secret")
    wa_factory.get_whatsapp_provider.cache_clear()
    try:
        body = (
            b'{"entry":[{"changes":[{"value":{"messages":[{"from":"5511900000099",'
            b'"id":"wamid.X","type":"text","text":{"body":"oi"}}]}}]}]}'
        )

        wrong = await client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
        )
        assert wrong.status_code == 401

        correct_signature = "sha256=" + hmac.new(b"top-secret", body, hashlib.sha256).hexdigest()
        right = await client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": correct_signature},
        )
        assert right.status_code == 200
    finally:
        # Always restore, even on assertion failure — a leaked lru_cache'd
        # "official" provider would silently break every later test.
        wa_factory.get_whatsapp_provider.cache_clear()


@pytest.mark.asyncio
async def test_webhook_rejects_malformed_json_body(client):
    response = await client.post(
        "/api/webhooks/whatsapp", content=b"not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422


# --- Duplicate message protection --------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_external_id_is_not_reprocessed(client, db_engine):
    payload = {"from": "5511900000077@c.us", "body": "oi", "notifyName": "Dup", "id": "wamid-dup-1"}

    first = await client.post("/api/webhooks/whatsapp", json=payload)
    assert first.status_code == 200
    first_id = first.json()["message_id"]

    second = await client.post("/api/webhooks/whatsapp", json=payload)
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert second.json()["message_id"] == first_id

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        rows = (
            (await session.execute(select(Message).where(Message.external_id == "wamid-dup-1")))
            .scalars()
            .all()
        )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_delivery_recovers_from_integrity_error(client, db_engine, monkeypatch):
    """Simulate the race: the dedup pre-check misses (another request is
    mid-flight with the same external_id), so the insert collides at the DB
    level — the webhook must recover, not 500."""
    from repositories.message import MessageRepository

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    # Plant the "concurrent" row directly, as if another request just won the race.
    from models.contact import Contact
    from models.message import Message as MessageModel
    from models.message import MessageDirection, MessageMediaType

    async with factory() as session:
        contact = Contact(name="Race", phone="5511900000088")
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        winner = MessageModel(
            contact_id=contact.id,
            direction=MessageDirection.INBOUND,
            media_type=MessageMediaType.TEXT,
            content="ja chegou",
            external_id="wamid-race-1",
        )
        session.add(winner)
        await session.commit()
        await session.refresh(winner)
        winner_id = winner.id

    original_find_one = MessageRepository.find_one
    calls = {"count": 0}

    async def flaky_find_one(self, **filters):
        calls["count"] += 1
        if calls["count"] == 1:
            return None  # pretend the dedup pre-check missed the race
        return await original_find_one(self, **filters)

    monkeypatch.setattr(MessageRepository, "find_one", flaky_find_one)

    response = await client.post(
        "/api/webhooks/whatsapp",
        json={"from": "5511900000088@c.us", "body": "ja chegou", "notifyName": "Race", "id": "wamid-race-1"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "duplicate"
    assert response.json()["message_id"] == winner_id
