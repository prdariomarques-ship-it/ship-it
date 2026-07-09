from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_whatsapp_webhook_stores_message_and_contact(client, auth_headers):
    with patch("webhooks.router.workflow_service.trigger", new=AsyncMock(return_value={})):
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

    messages = await client.get("/api/messages", headers=auth_headers)
    assert messages.json()[0]["content"] == "Olá, tudo bem?"
    assert messages.json()[0]["direction"] == "inbound"


@pytest.mark.asyncio
async def test_webhook_reuses_existing_contact(client, auth_headers):
    with patch("webhooks.router.workflow_service.trigger", new=AsyncMock(return_value={})):
        for body in ("primeira", "segunda"):
            await client.post(
                "/api/webhooks/whatsapp",
                json={"from": "5511911112222@c.us", "body": body, "notifyName": "Ana"},
            )

    contacts = await client.get("/api/contacts", headers=auth_headers)
    assert len(contacts.json()) == 1

    messages = await client.get("/api/messages", headers=auth_headers)
    assert len(messages.json()) == 2
