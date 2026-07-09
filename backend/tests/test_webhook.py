import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.job import Job


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
    response = await client.post("/api/webhooks/whatsapp", json={"event": "battery", "data": {}})
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
