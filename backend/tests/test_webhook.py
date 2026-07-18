import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from events.bus import event_bus
from models.job import Job
from models.message import Message


@pytest.mark.asyncio
async def test_whatsapp_webhook_stores_message_and_contact(client, auth_headers):
    response = await client.post(
        "/api/webhooks/whatsapp",
        json={
            "from": "5511988887777@c.us",
            "body": "Olá, tudo bem?",
            "notifyName": "João",
            "id": "wamid-123",
            "type": "text",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "received"

    contacts = await client.get("/api/contacts", headers=auth_headers)
    assert contacts.json()[0]["phone"] == "5511988887777"
    assert contacts.json()[0]["last_interaction_at"] is not None

    messages = await client.get("/api/messages", headers=auth_headers)
    assert messages.json()[0]["content"] == "Olá, tudo bem?"
    assert messages.json()[0]["direction"] == "inbound"
    # Regression: this used to be missing, forcing the UI to show the raw
    # numeric contact_id instead of who the conversation was actually with.
    assert messages.json()[0]["contact_name"] == "João"
    assert messages.json()[0]["contact_phone"] == "5511988887777"


@pytest.mark.asyncio
async def test_webhook_enqueues_workflow_job(client, db_engine):
    await client.post(
        "/api/webhooks/whatsapp",
        json={"from": "5511933334444@c.us", "body": "oi", "notifyName": "Bia"},
    )

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        jobs = (await session.execute(select(Job))).scalars().all()
    names = [job.name for job in jobs]
    assert "workflow.trigger" in names


@pytest.mark.asyncio
async def test_webhook_reuses_existing_contact(client, auth_headers):
    for body in ("primeira", "segunda"):
        await client.post(
            "/api/webhooks/whatsapp",
            json={"from": "5511911112222@c.us", "body": body, "notifyName": "Ana"},
        )

    contacts = await client.get("/api/contacts", headers=auth_headers)
    assert len(contacts.json()) == 1

    messages = await client.get("/api/messages", headers=auth_headers)
    assert len(messages.json()) == 2


@pytest.mark.asyncio
async def test_webhook_ignores_non_message_events(client):
    response = await client.post(
        "/api/webhooks/whatsapp", json={"event": "battery", "data": {}}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


# --- Delivery acks: a receipt for a message this app previously sent --------
@pytest.mark.asyncio
async def test_webhook_delivery_ack_updates_message_status(client, db_engine):
    inbound = await client.post(
        "/api/webhooks/whatsapp",
        json={
            "from": "5511900001234@c.us",
            "body": "oi",
            "notifyName": "Ack",
            "id": "wamid-ack-1",
        },
    )
    message_id = inbound.json()["message_id"]

    received = []

    async def on_ack(event):
        received.append(event.payload)

    event_bus.subscribe("whatsapp.message_delivery_ack", on_ack)

    response = await client.post(
        "/api/webhooks/whatsapp",
        json={"event": "onAck", "data": {"id": "wamid-ack-1", "ack": 2}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "delivery_ack"
    assert received == [
        {"provider": "openwa", "external_id": "wamid-ack-1", "status": "delivered"}
    ]

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        message = await session.get(Message, message_id)
    assert message.delivery_status.value == "delivered"


@pytest.mark.asyncio
async def test_webhook_delivery_ack_for_unknown_message_still_acks(client):
    """An ack for a message we never persisted (e.g. sent before this
    feature existed) must not 500 — just publish the event and move on."""
    response = await client.post(
        "/api/webhooks/whatsapp",
        json={"event": "onAck", "data": {"id": "unknown-external-id", "ack": 1}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "delivery_ack"


# --- Connection/session events: state changes reported by the gateway ------
@pytest.mark.asyncio
async def test_webhook_connection_event_publishes_session_changed(client):
    received = []

    async def on_session_changed(event):
        received.append(event.payload)

    event_bus.subscribe("whatsapp.session_changed", on_session_changed)

    response = await client.post(
        "/api/webhooks/whatsapp", json={"event": "onStateChanged", "data": "CONNECTED"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "session_event"
    assert received == [
        {"provider": "openwa", "status": "connected", "detail": "CONNECTED"}
    ]


@pytest.mark.asyncio
async def test_webhook_connection_event_reports_auth_expired(client):
    from observability.metrics import WHATSAPP_SESSION_STATUS

    response = await client.post(
        "/api/webhooks/whatsapp", json={"event": "onStateChanged", "data": "UNPAIRED"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "session_event"
    assert WHATSAPP_SESSION_STATUS.labels("openwa")._value.get() == 0
