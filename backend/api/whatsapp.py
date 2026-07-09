"""Outbound WhatsApp endpoints (text, image, PDF/file, audio, location).

All sends go through the configured provider (Strategy) and every outbound
message is persisted and fed into the contact memory.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import CurrentUser
from database.session import get_db
from memory.contact_memory import contact_memory_service
from models.message import Message, MessageDirection, MessageMediaType
from providers.whatsapp.base import WhatsAppProviderError, normalize_phone
from providers.whatsapp.factory import get_whatsapp_provider
from repositories.contact import ContactRepository

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class SendTextRequest(BaseModel):
    to: str = Field(description="Phone in international format, e.g. 5511999999999")
    content: str = Field(min_length=1)


class SendMediaRequest(BaseModel):
    to: str
    url: str = Field(description="Public URL of the media file")
    filename: str = "file"
    caption: str = ""


class SendLocationRequest(BaseModel):
    to: str
    latitude: float
    longitude: float
    caption: str = ""


class SendResponse(BaseModel):
    status: str = "sent"
    message_id: int | None = None


async def _persist_outbound(
    db: AsyncSession, phone: str, content: str, media_type: MessageMediaType
) -> Message:
    clean_phone = normalize_phone(phone)
    contact = await ContactRepository(db).get_or_create_by_phone(clean_phone)

    message = Message(
        contact_id=contact.id,
        direction=MessageDirection.OUTBOUND,
        media_type=media_type,
        content=content,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    await contact_memory_service.record_interaction(db, contact, content, source="whatsapp")
    return message


def _bad_gateway(exc: WhatsAppProviderError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.post("/send-text", response_model=SendResponse)
async def send_text(payload: SendTextRequest, db: DbSession, _: CurrentUser) -> SendResponse:
    try:
        await get_whatsapp_provider().send_text(payload.to, payload.content)
    except WhatsAppProviderError as exc:
        raise _bad_gateway(exc) from exc
    message = await _persist_outbound(db, payload.to, payload.content, MessageMediaType.TEXT)
    return SendResponse(message_id=message.id)


@router.post("/send-image", response_model=SendResponse)
async def send_image(payload: SendMediaRequest, db: DbSession, _: CurrentUser) -> SendResponse:
    try:
        await get_whatsapp_provider().send_image(
            payload.to, payload.url, payload.filename, payload.caption
        )
    except WhatsAppProviderError as exc:
        raise _bad_gateway(exc) from exc
    message = await _persist_outbound(db, payload.to, payload.url, MessageMediaType.IMAGE)
    return SendResponse(message_id=message.id)


@router.post("/send-file", response_model=SendResponse)
async def send_file(payload: SendMediaRequest, db: DbSession, _: CurrentUser) -> SendResponse:
    try:
        await get_whatsapp_provider().send_file(
            payload.to, payload.url, payload.filename, payload.caption
        )
    except WhatsAppProviderError as exc:
        raise _bad_gateway(exc) from exc
    message = await _persist_outbound(db, payload.to, payload.url, MessageMediaType.PDF)
    return SendResponse(message_id=message.id)


@router.post("/send-audio", response_model=SendResponse)
async def send_audio(payload: SendMediaRequest, db: DbSession, _: CurrentUser) -> SendResponse:
    try:
        await get_whatsapp_provider().send_audio(payload.to, payload.url)
    except WhatsAppProviderError as exc:
        raise _bad_gateway(exc) from exc
    message = await _persist_outbound(db, payload.to, payload.url, MessageMediaType.AUDIO)
    return SendResponse(message_id=message.id)


@router.post("/send-location", response_model=SendResponse)
async def send_location(payload: SendLocationRequest, db: DbSession, _: CurrentUser) -> SendResponse:
    try:
        await get_whatsapp_provider().send_location(
            payload.to, payload.latitude, payload.longitude, payload.caption
        )
    except WhatsAppProviderError as exc:
        raise _bad_gateway(exc) from exc
    message = await _persist_outbound(
        db, payload.to, f"{payload.latitude},{payload.longitude}", MessageMediaType.LOCATION
    )
    return SendResponse(message_id=message.id)
