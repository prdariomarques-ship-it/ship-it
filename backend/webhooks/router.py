"""Inbound webhooks — the entry point of the WhatsApp end-to-end flow:

    WhatsApp -> Provider -> webhook -> persist -> publish event
             -> job queue -> AI Orchestrator -> agent (memory + tools)
             -> reply job -> Provider -> WhatsApp

The configured provider normalizes its own webhook payload; we persist the
contact + message, feed the contact memory, and enqueue the automatic reply
(`whatsapp.process_inbound`) through the durable job queue — retry, timeout
and failure handling all come from that existing queue, not from new code
here. The legacy n8n hand-off (`workflow.trigger`) keeps running alongside it
for anyone using n8n for additional automation.
"""
import hmac
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_db
from events.bus import event_bus
from jobs.service import JobService
from memory.contact_memory import contact_memory_service
from models.message import Message, MessageDeliveryStatus, MessageDirection, MessageMediaType
from observability.metrics import record_whatsapp_session_status
from orchestrator.priority import Priority, quick_priority_hint
from providers.whatsapp.base import ConnectionStatus, DeliveryStatus, WhatsAppProvider
from providers.whatsapp.factory import get_whatsapp_provider
from repositories.contact import ContactRepository
from repositories.message import MessageRepository
from services.audit import record_log
from services.rate_limit import rate_limiter
from utils.config import get_settings
from utils.logging import get_logger
from webhooks.middleware import WebhookSecurity

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_MEDIA_TYPES = {media.value for media in MessageMediaType}

_DELIVERY_STATUS_MAP = {
    DeliveryStatus.SENT: MessageDeliveryStatus.SENT,
    DeliveryStatus.DELIVERED: MessageDeliveryStatus.DELIVERED,
    DeliveryStatus.READ: MessageDeliveryStatus.READ,
    DeliveryStatus.FAILED: MessageDeliveryStatus.FAILED,
}

# Non-urgent messages keep the pre-Fase-4.2 delay of 0 (immediately due);
# urgent ones are scheduled slightly in the past so they both become due
# right away and sort ahead of same-instant jobs (due_jobs orders by
# scheduled_at ascending) — a real, minimal queue-jump, not a simulated one.
_PRIORITY_ENQUEUE_DELAY: dict[Priority, float] = {
    Priority.URGENT: -5.0,
    Priority.HIGH: 0.0,
    Priority.NORMAL: 0.0,
    Priority.LOW: 0.0,
}


class WebhookAck(BaseModel):
    status: str = "received"
    message_id: int | None = None


async def _handle_connection_event(
    db: AsyncSession, provider: WhatsAppProvider, payload: dict
) -> WebhookAck | None:
    """Session state change (connected/disconnected/logged out). The provider
    only reports what happened; deciding to log/alert/record is the app's job."""
    event = provider.parse_connection_event(payload)
    if event is None:
        return None

    record_whatsapp_session_status(provider.name, connected=event.status == ConnectionStatus.CONNECTED)
    level = "warning" if event.status != ConnectionStatus.CONNECTED else "info"
    await record_log(
        db,
        source=f"whatsapp:{provider.name}",
        message=f"Session {event.status.value} ({event.detail})",
        level=level,
        payload={"provider": provider.name, "status": event.status.value, "detail": event.detail},
    )
    await event_bus.publish(
        "whatsapp.session_changed",
        {"provider": provider.name, "status": event.status.value, "detail": event.detail},
    )
    if event.status == ConnectionStatus.AUTH_EXPIRED:
        logger.error(
            "WhatsApp session for provider %s needs re-authentication (%s) — "
            "a human needs to re-pair the device (e.g. re-scan the QR code).",
            provider.name, event.detail,
        )
    return WebhookAck(status="session_event")


async def _handle_delivery_ack(
    db: AsyncSession, provider: WhatsAppProvider, payload: dict
) -> WebhookAck | None:
    """Delivery/read receipt for a message this app sent."""
    ack = provider.parse_delivery_ack(payload)
    if ack is None:
        return None

    message = await MessageRepository(db).get_by_external_id(ack.external_id)
    if message is not None:
        await MessageRepository(db).update(message, delivery_status=_DELIVERY_STATUS_MAP[ack.status])

    await event_bus.publish(
        "whatsapp.message_delivery_ack",
        {"provider": provider.name, "external_id": ack.external_id, "status": ack.status.value},
    )
    return WebhookAck(status="delivery_ack")


def _verify_webhook_security(provider: WhatsAppProvider, raw_body: bytes, headers) -> None:
    """Two independent checks, both provider-agnostic in shape:
    a shared-secret token (works for any gateway) and, when the provider
    implements one, a real per-payload cryptographic signature."""
    settings = get_settings()
    if settings.webhook_secret:
        token = headers.get("x-webhook-token", "")
        if not hmac.compare_digest(token, settings.webhook_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token")
    if not provider.verify_signature(raw_body, headers):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")


@router.post(
    "/whatsapp",
    response_model=WebhookAck,
    summary="Inbound WhatsApp webhook",
    description=(
        "Body shape depends on the configured WHATSAPP_PROVIDER (OpenWA, Baileys, "
        "Evolution API or the WhatsApp Cloud API); the request is read as raw bytes "
        "here so the configured provider's own signature scheme can be verified."
    ),
)
async def whatsapp_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebhookAck:
    provider = get_whatsapp_provider()
    raw_body = await request.body()
    
    # Validação de segurança por provider (nova implementação)
    if not WebhookSecurity.validate(provider.name, request, raw_body):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid webhook signature for provider {provider.name}"
        )
    
    # Manter validação legacy para compatibilidade (webhook_secret global)
    _verify_webhook_security(provider, raw_body, request.headers)

    try:
        payload = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid JSON body"
        ) from exc
    inbound = provider.parse_webhook(payload)
    if inbound is None:
        connection_ack = await _handle_connection_event(db, provider, payload)
        if connection_ack is not None:
            return connection_ack
        delivery_ack = await _handle_delivery_ack(db, provider, payload)
        if delivery_ack is not None:
            return delivery_ack
        return WebhookAck(status="ignored")

    # Idempotency: a provider redelivering the same message (a common webhook
    # retry pattern) must not be processed twice — no double reply, no double
    # embedding, no double job. Checked here and enforced by a unique
    # constraint on messages.external_id (belt and suspenders for concurrent
    # redeliveries racing this check).
    if inbound.external_id:
        existing = await MessageRepository(db).find_one(external_id=inbound.external_id)
        if existing is not None:
            return WebhookAck(status="duplicate", message_id=existing.id)

    contacts = ContactRepository(db)
    contact = await contacts.get_or_create_by_phone(inbound.phone, inbound.sender_name or None)

    media_type = inbound.media_type if inbound.media_type in _MEDIA_TYPES else "text"
    message = Message(
        contact_id=contact.id,
        direction=MessageDirection.INBOUND,
        media_type=MessageMediaType(media_type),
        content=inbound.text,
        external_id=inbound.external_id or None,
        provider_timestamp=inbound.timestamp,
    )
    db.add(message)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a redelivery race against another request for the same
        # external_id: the other request's row is the record of truth.
        await db.rollback()
        existing = await MessageRepository(db).find_one(external_id=inbound.external_id)
        if existing is not None:
            return WebhookAck(status="duplicate", message_id=existing.id)
        raise
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

    settings = get_settings()
    if settings.auto_reply_enabled and media_type == "text" and inbound.text.strip():
        # Loop/flood breaker: a runaway automation on the other end (or a
        # genuine bug) must not turn into an unbounded reply storm for one
        # contact. Reuses the same RateLimiter as HTTP throttling, just a
        # separate namespace and threshold.
        allowed = await rate_limiter.is_allowed(
            f"auto-reply:{contact.id}",
            limit=settings.auto_reply_max_per_contact_per_minute,
            window_seconds=60,
        )
        if allowed:
            # Priority de execução (Fase 4.2): a cheap, non-LLM keyword hint
            # decides scheduled_at. Non-urgent messages keep delay_seconds=0
            # (identical to pre-4.2 behaviour); urgent ones are scheduled a
            # few seconds in the past, which both makes them immediately due
            # and — since due_jobs orders by scheduled_at ascending — lets
            # them sort ahead of anything else already sitting in the queue.
            # The Cognitive Pipeline still runs the full (LLM-backed)
            # PriorityEngine once the job executes; this only affects when
            # it gets picked up, not how it's handled.
            delay_seconds = _PRIORITY_ENQUEUE_DELAY[quick_priority_hint(inbound.text)]
            await jobs.enqueue(
                "whatsapp.process_inbound",
                {"contact_id": contact.id, "message_id": message.id},
                delay_seconds=delay_seconds,
            )
        else:
            logger.warning("Auto-reply throttled for contact %s (loop/flood guard)", contact.id)

    # Decoupling point: the webhook doesn't know (or care) who reacts to a new
    # inbound message — the auto-reply job above, n8n via workflow.trigger,
    # and anyone else subscribed to this event (the future AI Console,
    # analytics, a second automation).
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
