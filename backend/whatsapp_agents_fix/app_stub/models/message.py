"""FAKE -- extended for webhooks/router.py's module-level needs
(_MEDIA_TYPES, _DELIVERY_STATUS_MAP). Real model file was not part of the
three sources this delivery was built from."""

from enum import Enum


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageDeliveryStatus(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class MessageMediaType(str, Enum):
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    DOCUMENT = "document"
    VIDEO = "video"


class Message:
    """FAKE -- an empty placeholder class, not a real ORM model."""
