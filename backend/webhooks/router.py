"""Inbound webhooks — the entry point of the WhatsApp → n8n → agent flow.

Flow: OpenWA posts the message here; we persist contact + message, then forward
the normalized event to n8n, which orchestrates the AI agent and the reply.
"""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_db
from models.contact import Contact
from models.message import Message, MessageDirection, MessageMediaType
from services.audit import record_log
from webhooks.schemas import WebhookAck, WhatsAppInboundMessage
from workflows.service import WorkflowError, workflow_service
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_MEDIA_TYPES = {media.value for media in MessageMediaType}


async def _forward_to_n8n(payload: dict) -> None:
    try:
        await workflow_service.trigger("whatsapp-inbound", payload)
    except WorkflowError:
        logger.warning("n8n unreachable; inbound message stored but not forwarded")


@router.post("/whatsapp", response_model=WebhookAck)
async def whatsapp_webhook(
    payload: WhatsAppInboundMessage,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebhookAck:
    phone = payload.from_number.split("@")[0]

    contact = (await db.execute(select(Contact).where(Contact.phone == phone))).scalar_one_or_none()
    if contact is None:
        contact = Contact(name=payload.sender_name or phone, phone=phone)
        db.add(contact)
        await db.flush()

    media_type = payload.media_type if payload.media_type in _MEDIA_TYPES else "text"
    message = Message(
        contact_id=contact.id,
        direction=MessageDirection.INBOUND,
        media_type=MessageMediaType(media_type),
        content=payload.body,
        external_id=payload.message_id or None,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    await record_log(
        db,
        source="webhook:whatsapp",
        message=f"Inbound message from {phone}",
        payload={"contact_id": contact.id, "message_id": message.id},
    )

    background_tasks.add_task(
        _forward_to_n8n,
        {
            "contact_id": contact.id,
            "message_id": message.id,
            "phone": phone,
            "name": contact.name,
            "body": payload.body,
            "media_type": media_type,
        },
    )
    return WebhookAck(message_id=message.id)
