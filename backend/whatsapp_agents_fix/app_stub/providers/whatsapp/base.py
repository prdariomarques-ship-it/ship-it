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
