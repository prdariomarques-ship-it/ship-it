from pydantic import BaseModel, Field


class WhatsAppInboundMessage(BaseModel):
    """Normalized inbound message from OpenWA (via its webhook)."""

    from_number: str = Field(alias="from", description="Sender in OpenWA format, e.g. 5511999999999@c.us")
    body: str = ""
    sender_name: str = Field(default="", alias="notifyName")
    message_id: str = Field(default="", alias="id")
    media_type: str = Field(default="text", alias="type")

    model_config = {"populate_by_name": True}


class WebhookAck(BaseModel):
    status: str = "received"
    message_id: int | None = None
