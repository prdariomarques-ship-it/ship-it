"""Provider-agnostic WhatsApp contract (Strategy pattern).

A Provider's only job is translation and transport:
(a) send every media type through its own API,
(b) normalize its webhook payload into the shared internal models
    (`InboundMessage`, `ConnectionEvent`, `DeliveryAck`) — the rest of the
    application never sees a provider-specific shape,
(c) verify its own webhook's cryptographic signature scheme, if it has one,
(d) report whether its gateway is reachable (`health_check`).

No business logic belongs here: no database access, no job enqueueing, no
Event Bus, no memory. The webhook route decides what to *do* with a
translated event; the provider only decides *what the event means*.
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime
from enum import Enum

import httpx
from pydantic import BaseModel

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class WhatsAppProviderError(RuntimeError):
    pass


def extract_receipt_id(response: object) -> str | None:
    """Best-effort extraction of the provider-assigned message id from a
    send_text/send_image/... response -- `response["key"]["id"]`, the
    shape shared by every provider built on the WhatsApp Web protocol
    (Baileys, and anything wrapping it, like Evolution API).

    Returns None -- never raises -- for anything that doesn't have this
    shape (including a fake/test provider returning None, or a future
    provider with a different contract). A caller must treat None exactly
    like "no receipt available": the send stays `needs_review`, never
    promoted to `sent` on a guess. See jobs/handlers.py's send_whatsapp_text."""
    if not isinstance(response, Mapping):
        return None
    key = response.get("key")
    if not isinstance(key, Mapping):
        return None
    receipt_id = key.get("id")
    return receipt_id if isinstance(receipt_id, str) and receipt_id else None


class InboundMessage(BaseModel):
    """Webhook payload normalized across providers."""

    phone: str  # digits only, international format
    text: str = ""
    sender_name: str = ""
    external_id: str = ""
    media_type: str = "text"
    # The provider's own event timestamp, when it reports one. Webhook
    # redeliveries or network jitter can land messages out of arrival order;
    # ordering by this (falling back to arrival order when absent) keeps
    # conversation history and agent context chronologically correct.
    timestamp: datetime | None = None
    # Review finding (new, 2026-10-09): webhooks/router.py and jobs/handlers.py
    # both read `inbound.instance` extensively (loop guards, pause scoping,
    # Message.whatsapp_instance) and router.py also reads `inbound.media_key`
    # for owner-audio download -- but this model never declared either
    # field, so every real webhook call would raise AttributeError the
    # moment either was read. Added here with evidence from the Evolution
    # webhook shape itself (`{event, instance, data: {...}}`, see
    # evolution/provider.py's parse_webhook comment). `media_key` is left
    # unpopulated by any provider for now -- see providers/whatsapp/evolution/
    # provider.py's parse_webhook docstring for why extraction isn't
    # implemented yet (no download_media method exists anywhere either).
    instance: str = ""
    media_key: str | None = None


class ConnectionStatus(str, Enum):
    """Session-level state of a provider's WhatsApp connection."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    AUTH_EXPIRED = "auth_expired"  # session logged out / needs re-pairing
    RECONNECTING = "reconnecting"
    UNKNOWN = "unknown"


class ConnectionEvent(BaseModel):
    """Session state change reported by the provider (not a chat message)."""

    status: ConnectionStatus
    detail: str = ""


class DeliveryStatus(str, Enum):
    """Delivery confirmation for a previously sent message, when the
    provider's transport supports read receipts / delivery acks."""

    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class DeliveryAck(BaseModel):
    """Delivery/read receipt for a message this app sent, matched by
    `external_id` (the id the provider assigned when the send happened)."""

    external_id: str
    status: DeliveryStatus


class WhatsAppProvider(ABC):
    """Strategy interface implemented by every WhatsApp integration."""

    name: str

    @abstractmethod
    async def send_text(self, to: str, content: str) -> dict: ...

    @abstractmethod
    async def send_image(
        self, to: str, url: str, filename: str = "image", caption: str = ""
    ) -> dict: ...

    @abstractmethod
    async def send_file(
        self, to: str, url: str, filename: str = "file", caption: str = ""
    ) -> dict: ...

    @abstractmethod
    async def send_audio(self, to: str, url: str) -> dict: ...

    @abstractmethod
    async def send_location(
        self, to: str, latitude: float, longitude: float, caption: str = ""
    ) -> dict: ...

    @abstractmethod
    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        """Normalize an inbound webhook payload; None for non-message events."""

    def parse_connection_event(self, payload: dict) -> ConnectionEvent | None:
        """Recognize a session-level event (connected/disconnected/logged
        out) in a webhook payload. Default: this provider's webhook carries
        no such events — override where the gateway reports session state.
        """
        return None

    def parse_delivery_ack(self, payload: dict) -> DeliveryAck | None:
        """Recognize a delivery/read receipt in a webhook payload. Default:
        not supported by this provider's transport."""
        return None

    async def health_check(self) -> bool:
        """Best-effort reachability probe for the gateway. Default: assume
        healthy (no cheap generic probe exists across every gateway type);
        override with a real ping where the gateway exposes one."""
        return True

    def verify_signature(self, raw_body: bytes, headers: Mapping[str, str]) -> bool:
        """Per-payload cryptographic signature check, when the provider's
        webhook supports one (e.g. Meta's X-Hub-Signature-256).

        Default: no such scheme for this provider — the shared WEBHOOK_SECRET
        token (checked separately, provider-agnostically, in the webhook
        route) is the only guard. Override in providers that sign requests.
        """
        return True

    async def _request(
        self,
        method: str,
        url: str,
        json_body: dict | None = None,
        headers: dict | None = None,
        timeout: float = 30,
        max_attempts: int | None = None,
    ) -> dict:
        """Shared HTTP helper: uniform error translation, retry with
        exponential backoff for transient failures, and availability metrics
        — every provider gets this for free since they all call through here
        rather than using httpx directly.

        `max_attempts` overrides the configured default — pass 1 for calls
        that must stay fast and single-shot (e.g. a readiness probe polled
        frequently by an orchestrator should never block for several seconds
        retrying a gateway that's genuinely down)."""
        from observability.metrics import record_whatsapp_request

        settings = get_settings()
        max_attempts = (
            max_attempts
            if max_attempts is not None
            else settings.whatsapp_request_max_attempts
        )
        last_exc: httpx.HTTPError | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.request(
                        method, url, json=json_body, headers=headers
                    )
                    response.raise_for_status()
                record_whatsapp_request(self.name, "ok")
                if response.headers.get("content-type", "").startswith(
                    "application/json"
                ):
                    return response.json()
                return {"status": "ok"}
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= max_attempts:
                    break
                backoff = settings.whatsapp_request_backoff_seconds * (
                    2 ** (attempt - 1)
                )
                logger.warning(
                    "%s provider call failed (%s %s), attempt %s/%s, retrying in %ss: %s",
                    self.name,
                    method,
                    url,
                    attempt,
                    max_attempts,
                    backoff,
                    exc,
                )
                await asyncio.sleep(backoff)

        record_whatsapp_request(self.name, "error")
        logger.error(
            "%s provider call failed (%s %s) after %s attempts: %s",
            self.name,
            method,
            url,
            max_attempts,
            last_exc,
        )
        raise WhatsAppProviderError(
            f"{self.name} request failed: {last_exc}"
        ) from last_exc


def normalize_phone(raw: str) -> str:
    """Strip provider suffixes/symbols: '5511999@c.us' -> '5511999'."""
    return raw.split("@")[0].split(":")[0].lstrip("+")


# Baileys-style message envelopes are shared by every gateway built on the
# Baileys library (Evolution API included) — keep the mapping in one place.
BAILEYS_MEDIA_BY_MESSAGE_KEY = {
    "conversation": "text",
    "extendedTextMessage": "text",
    "imageMessage": "image",
    "documentMessage": "pdf",
    "audioMessage": "audio",
    "locationMessage": "location",
}


def extract_baileys_content(message: dict) -> tuple[str, str]:
    """Return (media_type, text) from a Baileys-style `message` object."""
    for message_key, mapped_type in BAILEYS_MEDIA_BY_MESSAGE_KEY.items():
        if message_key in message:
            inner = message[message_key]
            if isinstance(inner, str):
                return mapped_type, inner
            if isinstance(inner, dict):
                return mapped_type, inner.get("text", "") or inner.get("caption", "")
            return mapped_type, ""
    return "text", ""
