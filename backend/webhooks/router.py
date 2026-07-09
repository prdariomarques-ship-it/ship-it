"""Inbound webhooks — the entry point of the WhatsApp → n8n → agent flow.

The configured provider normalizes its own webhook payload; we persist the
contact + message, feed the contact memory, and hand off orchestration to n8n
through the durable job queue (retry included).
"""
import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_db
from events.bus import event_bus
from jobs.service import JobService
from memory.contact_memory import contact_memory_service
from models.message import Message, MessageDirection, MessageMediaType
from repositories.contact import ContactRepository
from providers.whatsapp.factory import get_whatsapp_provider
from services.audit import record_log
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_MEDIA_TYPES = {media.value for media in MessageMediaType}


class WebhookAck(BaseModel):
    status: str = "received"
    message_id: int | None = None


def verify_webhook_token(x_webhook_token: Annotated[str | None, Header()] = None) -> None:
    """When WEBHOOK_SECRET is configured, inbound webhooks must present it."""
    secret = get_settings().webhook_secret
    if secret and not hmac.compare_digest(x_webhook_token or "", secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token"
        )


@router.post("/whatsapp", response_model=WebhookAck, dependencies=[Depends(verify_webhook_token)])
async def whatsapp_webhook(
    payload: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebhookAck:
    provider = get_whatsapp_provider()
    inbound = provider.parse_webhook(payload)
    if inbound is None:
        return WebhookAck(status="ignored")

    contacts = ContactRepository(db)
    contact = await contacts.get_or_create_by_phone(inbound.phone, inbound.sender_name or None)

    media_type = inbound.media_type if inbound.media_type in _MEDIA_TYPES else "text"
    message = Message(
        contact_id=contact.id,
        direction=MessageDirection.INBOUND,
        media_type=MessageMediaType(media_type),
        content=inbound.text,
        external_id=inbound.external_id or None,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    await record_log(
        db,
        source="webhook:whatsapp",
        message=f"Inbound message from {inbound.phone} via {provider.name}",
        payload={"contact_id": contact.id, "message_id": message.id, "provider": provider.name},
    )

    summary_due = await contact_memory_service.record_interaction(
        db, contact, inbound.text, source="whatsapp"
    )

    jobs = JobService(db)
    await jobs.enqueue(
        "workflow.trigger",
        {
            "workflow": "whatsapp-inbound",
            "data": {
                "contact_id": contact.id,
                "message_id": message.id,
                "phone": inbound.phone,
                "name": contact.name,
                "body": inbound.text,
                "media_type": media_type,
            },
        },
    )
    if summary_due:
        await jobs.enqueue("contact.summarize", {"contact_id": contact.id})

    # Decoupling point: the webhook doesn't know (or care) who reacts to a new
    # inbound message — n8n via the job above, and anyone else subscribed to
    # this event (the future AI Console, analytics, a second automation).
    await event_bus.publish(
        "whatsapp.message_received",
        {
            "contact_id": contact.id,
            "message_id": message.id,
            "phone": inbound.phone,
            "provider": provider.name,
            "media_type": media_type,
        },
    )

    return WebhookAck(message_id=message.id)
