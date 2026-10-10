"""FAKE -- minimal shapes for webhooks/router.py's module-level
_DELIVERY_STATUS_MAP and type hints. Real provider contract file was not
part of the three sources this delivery was built from."""

from enum import Enum


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    AUTH_EXPIRED = "auth_expired"
    LOGGED_OUT = "logged_out"


class DeliveryStatus(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class InboundMessage:
    """FAKE -- an empty placeholder, only used as a type hint here."""


class WhatsAppProvider:
    """FAKE -- an empty placeholder base class, only used as a type hint."""


def normalize_phone(raw: str) -> str:
    """Mirrors the real backend/providers/whatsapp/base.py exactly (pure,
    no further dependencies) -- services/messaging.py's real
    persist_outbound_message calls this, and there is no copy of the rest
    of base.py here to drift from instead."""
    return raw.split("@")[0].split(":")[0].lstrip("+")


def extract_receipt_id(response: object) -> str | None:
    """NOT a placeholder like the rest of this file -- mirrors the real
    backend/providers/whatsapp/base.py's function exactly (review fix C),
    because jobs/handlers.py's send_whatsapp_text actually calls this and
    its behavior is what test_send_whatsapp_text_real_execution.py's
    receipt-capture tests verify. Keep in sync with the real file; there
    is no copy of the rest of base.py here to drift from instead."""
    if not isinstance(response, dict):
        return None
    key = response.get("key")
    if not isinstance(key, dict):
        return None
    receipt_id = key.get("id")
    return receipt_id if isinstance(receipt_id, str) and receipt_id else None
