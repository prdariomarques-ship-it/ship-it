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
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_db
from events.bus import event_bus
from jobs.service import JobService
from models.job import Job
from memory.contact_memory import contact_memory_service
from models.message import (
    Message,
    MessageDeliveryStatus,
    MessageDirection,
    MessageMediaType,
)
from observability.metrics import record_whatsapp_session_status
from orchestrator.priority import Priority, quick_priority_hint
from providers.stt.base import STTProviderError
from providers.stt.factory import get_stt_provider
from providers.whatsapp.base import (
    ConnectionStatus,
    DeliveryStatus,
    InboundMessage,
    WhatsAppProvider,
)
from providers.whatsapp.factory import get_whatsapp_provider
from repositories.contact import ContactRepository
from repositories.message import MessageRepository
from repositories.user import UserRepository
from services import conversation_control
from services.audit import record_log
from services.rate_limit import rate_limiter
from utils.config import get_settings
from utils.logging import get_logger

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


def _administered_instance_phones(settings) -> dict[str, str]:
    """Maps each administered instance identifier to the (digits-only)
    phone number that owns it, built only from phone settings that
    actually exist in utils/config.py today -- never a guessed or
    hardcoded number. Extend the `pairs` dict below, not the cross-talk
    check in whatsapp_webhook, when a new administered instance (e.g. a
    dedicated b2b-sales or azusa-church number) gets its own phone
    setting; the symmetric check already covers any instance added here.
    """
    pairs = {
        settings.evolution_personal_instance: settings.whatsapp_owner_alert_phone,
        settings.evolution_instance: settings.store_staff_notify_phone,
    }
    return {
        instance: "".join(ch for ch in (phone or "") if ch.isdigit())
        for instance, phone in pairs.items()
        if instance and phone
    }


async def _handle_connection_event(
    db: AsyncSession, provider: WhatsAppProvider, payload: dict
) -> WebhookAck | None:
    """Session state change (connected/disconnected/logged out). The provider
    only reports what happened; deciding to log/alert/record is the app's job."""
    event = provider.parse_connection_event(payload)
    if event is None:
        return None

    record_whatsapp_session_status(
        provider.name, connected=event.status == ConnectionStatus.CONNECTED
    )
    level = "warning" if event.status != ConnectionStatus.CONNECTED else "info"
    await record_log(
        db,
        source=f"whatsapp:{provider.name}",
        message=f"Session {event.status.value} ({event.detail})",
        level=level,
        payload={
            "provider": provider.name,
            "status": event.status.value,
            "detail": event.detail,
        },
    )
    await event_bus.publish(
        "whatsapp.session_changed",
        {
            "provider": provider.name,
            "status": event.status.value,
            "detail": event.detail,
        },
    )
    if event.status == ConnectionStatus.AUTH_EXPIRED:
        logger.error(
            "WhatsApp session for provider %s needs re-authentication (%s) — "
            "a human needs to re-pair the device (e.g. re-scan the QR code).",
            provider.name,
            event.detail,
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
        await MessageRepository(db).update(
            message, delivery_status=_DELIVERY_STATUS_MAP[ack.status]
        )

    await event_bus.publish(
        "whatsapp.message_delivery_ack",
        {
            "provider": provider.name,
            "external_id": ack.external_id,
            "status": ack.status.value,
        },
    )
    return WebhookAck(status="delivery_ack")


async def _transcribe_audio(
    db: AsyncSession, provider: WhatsAppProvider, inbound: InboundMessage
) -> str:
    """Best-effort speech-to-text for an inbound voice message, so it flows
    through the rest of the pipeline (twin, risk gate, cognitive pipeline)
    exactly like a typed message. Never raises: no STT provider configured,
    no media_key on this message, a download failure, or a transcription
    failure all just mean the message keeps its pre-existing behaviour
    (empty text, no auto-reply) instead of breaking webhook ingestion."""
    stt = get_stt_provider()
    if stt is None or not stt.enabled or inbound.media_key is None:
        return ""
    downloaded = await provider.download_media(inbound.media_key, instance=inbound.instance or None)
    if downloaded is None:
        return ""
    audio_bytes, mime_type = downloaded
    try:
        return await stt.transcribe(audio_bytes, mime_type)
    except STTProviderError as exc:
        logger.warning("Audio transcription failed: %s", exc)
        await record_log(
            db,
            source="webhook:whatsapp",
            level="warning",
            message="Falha ao transcrever áudio",
            payload={"phone": inbound.phone, "error": str(exc)},
        )
        return ""


async def _capture_human_reply(db: AsyncSession, provider: WhatsAppProvider, contact, inbound, media_type: str) -> WebhookAck:
    """The owner answered from his phone (provider fromMe echo): record it as
    a human message and clear the pending marker so the twin stays quiet.
    No auto-reply is ever enqueued from here. Owner audio gets a history-only
    transcription job in the same transaction as its message."""
    personal_instance = get_settings().evolution_personal_instance
    personal_empty_audio = media_type == 'audio' and (not (inbound.text or '').strip()) and bool(personal_instance) and (inbound.instance == personal_instance)
    own = None
    if not personal_empty_audio:
        own = await MessageRepository(db).find_unacknowledged_outbound(contact.id, inbound.text, instance=inbound.instance)
    if own is not None:
        own.external_id = inbound.external_id or None
        await db.commit()
        return WebhookAck(status='own_echo', message_id=own.id)
    message = Message(contact_id=contact.id, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType(media_type), content=inbound.text, external_id=inbound.external_id or None, provider_timestamp=inbound.timestamp, sent_by_human=True, whatsapp_instance=inbound.instance)
    db.add(message)
    if not personal_instance or inbound.instance == personal_instance:
        contact.awaiting_reply_since = None
    try:
        await db.flush()
        if media_type == 'audio' and (not (inbound.text or '').strip()) and personal_instance and (inbound.instance == personal_instance):
            db.add(Job(name='whatsapp.transcribe_owner_audio', payload={'message_id': message.id, 'media_key': inbound.media_key}))
        # Review fix (D): this is the real event that must pause automation
        # for this (contact, instance) -- a human (the owner or an
        # attendant) just replied from the actual phone. test_pause_fencing.py
        # proves the pause/claim_send fence works once triggered; nothing
        # before this fix ever triggered it from a real webhook. event_id is
        # the message's own id (stable, unique, available after flush
        # above) so a redelivered webhook for the SAME message can never
        # double-pause/double-bump the revision -- conversation_control.pause
        # is itself idempotent per event_id as a second layer, on top of the
        # IntegrityError/duplicate check this function already has.
        # Skipped only when the provider reports no instance at all (single-
        # instance deployments with an unset evolution_instance), since
        # conversation_control requires a nonempty scope.
        if inbound.instance:
            owner = await UserRepository(db).get_first_admin()
            if owner is not None:
                await conversation_control.pause(
                    db, contact.id, inbound.instance,
                    event_id=f'human-reply:{message.id}',
                    reason='owner_replied',
                    actor_id=owner.id,
                )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await MessageRepository(db).find_one(external_id=inbound.external_id)
        if existing is not None:
            return WebhookAck(status='duplicate', message_id=existing.id)
        raise
    await db.refresh(message)
    await record_log(db, source='webhook:whatsapp:human_reply', message=f'Owner reply captured for {inbound.phone} via {provider.name}', payload={'contact_id': contact.id, 'message_id': message.id})
    return WebhookAck(status='human_reply_captured', message_id=message.id)


def _verify_webhook_security(
    provider: WhatsAppProvider, raw_body: bytes, headers
) -> None:
    """Two independent checks, both provider-agnostic in shape:
    a shared-secret token (works for any gateway) and, when the provider
    implements one, a real per-payload cryptographic signature."""
    settings = get_settings()
    if settings.webhook_secret:
        token = headers.get("x-webhook-token", "")
        if not hmac.compare_digest(token, settings.webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token"
            )
    if not provider.verify_signature(raw_body, headers):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature"
        )


@router.get(
    "/whatsapp",
    summary="WhatsApp Cloud API webhook verification handshake",
    description=(
        "Meta requires this GET handshake before it will save a webhook "
        "subscription in the App Dashboard: it calls back with "
        "hub.mode=subscribe, hub.verify_token and hub.challenge, and expects "
        "hub.challenge echoed back verbatim (as plain text) when the token "
        "matches OFFICIAL_WEBHOOK_VERIFY_TOKEN. Irrelevant to gateways other "
        "than the Cloud API (official), but harmless to expose regardless of "
        "the active WHATSAPP_PROVIDER."
    ),
)
async def whatsapp_webhook_verify(request: Request) -> Response:
    settings = get_settings()
    mode = request.query_params.get("hub.mode", "")
    token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge", "")
    if (
        mode == "subscribe"
        and settings.official_webhook_verify_token
        and hmac.compare_digest(token, settings.official_webhook_verify_token)
    ):
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Webhook verification failed"
    )


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
    _verify_webhook_security(provider, raw_body, request.headers)

    try:
        payload = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid JSON body"
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Expected a JSON object")
    inbound = provider.parse_webhook(payload)
    if (
        inbound is not None
        and inbound.from_me
        and not get_settings().whatsapp_twin_mode_enabled
    ):
        # The owner's own messages are only captured for the digital twin.
        # Everywhere else (e.g. the store number) they stay ignored, exactly
        # as before -- otherwise the gateway's echo of every reply the app
        # itself sends would be stored a second time.
        inbound = None
    if inbound is None:
        connection_ack = await _handle_connection_event(db, provider, payload)
        if connection_ack is not None:
            return connection_ack
        delivery_ack = await _handle_delivery_ack(db, provider, payload)
        if delivery_ack is not None:
            return delivery_ack
        return WebhookAck(status="ignored")

    settings = get_settings()

    # No administered number may ever trigger automation on another one.
    # 2026-10-08 review: generalized from two hand-matched directional
    # pairs (store_phone-on-personal, owner_phone-on-main) to a symmetric
    # check over a registry -- the Twin/B2B loop happened between two
    # instances this older, narrower check never covered, since neither
    # "b2b-sales" nor "azusa-church" has its own phone setting checked
    # here. _administered_instance_phones only knows the two phone
    # settings that exist in utils/config.py today; if b2b-sales or
    # azusa-church get their own dedicated number in the future, adding it
    # to that one dict is enough -- this check does not need to change
    # again. Today, with only those two settings available, this is
    # behaviourally a superset of the old check (same two numbers, but
    # checked against every instance, not just one specific pair each).
    if not inbound.from_me:
        sender_phone = "".join(
            ch for ch in (inbound.phone or "") if ch.isdigit()
        )
        administered = _administered_instance_phones(settings)
        managed_cross_talk = bool(sender_phone) and any(
            sender_phone == phone and inbound.instance != instance_name
            for instance_name, phone in administered.items()
        )

        if managed_cross_talk:
            await record_log(
                db,
                source="webhook:whatsapp",
                level="info",
                message="Managed-number cross-talk ignored",
                payload={
                    "phone": inbound.phone,
                    "instance": inbound.instance,
                },
            )
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
    contact = await contacts.get_or_create_by_phone(
        inbound.phone, inbound.sender_name or None
    )

    media_type = inbound.media_type if inbound.media_type in _MEDIA_TYPES else "text"

    defer_audio = (
        media_type == "audio" and not inbound.from_me and not inbound.text.strip()
        and settings.stt_background_enabled
    )
    if media_type == "audio" and not inbound.from_me and not inbound.text.strip() and not defer_audio:
        inbound.text = await _transcribe_audio(db, provider, inbound)

    if inbound.from_me:
        return await _capture_human_reply(db, provider, contact, inbound, media_type)

    message = Message(
        contact_id=contact.id,
        direction=MessageDirection.INBOUND,
        media_type=MessageMediaType(media_type),
        content=inbound.text,
        external_id=inbound.external_id or None,
        provider_timestamp=inbound.timestamp,
        whatsapp_instance=inbound.instance,
    )
    db.add(message)
    try:
        if defer_audio:
            # The message and its audio job are committed together. A webhook
            # retry sees the existing message, never another transcription job.
            await db.flush()
            db.add(Job(name="whatsapp.transcribe_audio", payload={
                "message_id": message.id,
                "media_key": inbound.media_key,
            }))
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
        payload={
            "contact_id": contact.id,
            "message_id": message.id,
            "provider": provider.name,
        },
    )

    if defer_audio:
        return WebhookAck(message_id=message.id)
    await dispatch_inbound(db, provider, inbound, contact, message, media_type)
    return WebhookAck(message_id=message.id)


async def dispatch_inbound(db, provider, inbound, contact, message, media_type):
    """Shared continuation for typed messages and completed voice transcriptions."""
    settings = get_settings()
    is_personal_instance = (
        bool(settings.evolution_personal_instance)
        and inbound.instance == settings.evolution_personal_instance
    )

    summary_due = False

    # Qdrant/memória comercial só recebe conversas da loja.
    if not is_personal_instance:
        summary_due = await contact_memory_service.record_interaction(
            db, contact, inbound.text, source="whatsapp"
        )

    jobs = JobService(db)
    if not settings.store_whatsapp_enabled:
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
    # media_type stays "audio" (correct media tagging) even once transcribed
    # -- _transcribe_audio above already filled inbound.text when it worked,
    # so a transcribed voice note flows through exactly like a typed message.
    if (
        settings.auto_reply_enabled
        and media_type in ("text", "audio")
        and inbound.text.strip()
    ):
        # Loop/flood breaker: a runaway automation on the other end (or a
        # genuine bug) must not turn into an unbounded reply storm for one
        # contact. Reuses the same RateLimiter as HTTP throttling, just a
        # separate namespace and threshold.
        allowed = await rate_limiter.is_allowed(
            f"auto-reply:{inbound.instance}:{contact.id}",
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
            # Dual-instance deployments (evolution_personal_instance set)
            # reserve the twin for the owner's personal number: a dedicated
            # sales instance must always get the commercial agent, never an
            # impersonated reply. Single-instance deployments (the default,
            # personal instance unset) keep the flag's old, global meaning
            # unchanged.
            personal_instance = settings.evolution_personal_instance
            use_twin = settings.whatsapp_twin_mode_enabled and (
                not personal_instance or inbound.instance == personal_instance
            )
            if use_twin:
                # Digital twin: don't answer now. Mark the conversation as
                # waiting and let the check job decide after the idle timeout
                # (it is a no-op if the owner answered in the meantime).
                if contact.awaiting_reply_since is None:
                    contact.awaiting_reply_since = inbound.timestamp or datetime.now(
                        timezone.utc
                    )
                    await db.commit()
                await jobs.enqueue(
                    "whatsapp.twin_autopilot_check",
                    {
                        "contact_id": contact.id,
                        "message_id": message.id,
                        "instance": inbound.instance,
                    },
                    delay_seconds=settings.whatsapp_twin_idle_timeout_seconds,
                )
            else:
                delay_seconds = _PRIORITY_ENQUEUE_DELAY[
                    quick_priority_hint(inbound.text)
                ]
                await jobs.enqueue(
                    "whatsapp.process_inbound",
                    {
                        "contact_id": contact.id,
                        "message_id": message.id,
                        "instance": inbound.instance,
                    },
                    delay_seconds=delay_seconds,
                )
        else:
            logger.warning(
                "Auto-reply throttled for contact %s (loop/flood guard)", contact.id
            )

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
