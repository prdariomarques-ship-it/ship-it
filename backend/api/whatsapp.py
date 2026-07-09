"""Outbound WhatsApp endpoints (text, image, PDF/file, audio, location)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import CurrentUser
from database.session import get_db
from models.contact import Contact
from models.message import Message, MessageDirection, MessageMediaType
from services.whatsapp_service import WhatsAppError, whatsapp_service

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


def _chat_id(phone: str) -> str:
    return phone if "@" in phone else f"{phone}@c.us"


async def _persist_outbound(
    db: AsyncSession, phone: str, content: str, media_type: MessageMediaType
) -> Message:
    clean_phone = phone.split("@")[0]
    contact = (
        await db.execute(select(Contact).where(Contact.phone == clean_phone))
    ).scalar_one_or_none()
    if contact is None:
        contact = Contact(name=clean_phone, phone=clean_phone)
        db.add(contact)
        await db.flush()

    message = Message(
        contact_id=contact.id,
        direction=MessageDirection.OUTBOUND,
        media_type=media_type,
        content=content,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


def _service_unavailable(exc: WhatsAppError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.post("/send-text", response_model=SendResponse)
async def send_text(payload: SendTextRequest, db: DbSession, _: CurrentUser) -> SendResponse:
    try:
        await whatsapp_service.send_text(_chat_id(payload.to), payload.content)
    except WhatsAppError as exc:
        raise _service_unavailable(exc) from exc
    message = await _persist_outbound(db, payload.to, payload.content, MessageMediaType.TEXT)
    return SendResponse(message_id=message.id)


@router.post("/send-image", response_model=SendResponse)
async def send_image(payload: SendMediaRequest, db: DbSession, _: CurrentUser) -> SendResponse:
    try:
        await whatsapp_service.send_image(_chat_id(payload.to), payload.url, payload.filename, payload.caption)
    except WhatsAppError as exc:
        raise _service_unavailable(exc) from exc
    message = await _persist_outbound(db, payload.to, payload.url, MessageMediaType.IMAGE)
    return SendResponse(message_id=message.id)


@router.post("/send-file", response_model=SendResponse)
async def send_file(payload: SendMediaRequest, db: DbSession, _: CurrentUser) -> SendResponse:
    try:
        await whatsapp_service.send_file(_chat_id(payload.to), payload.url, payload.filename, payload.caption)
    except WhatsAppError as exc:
        raise _service_unavailable(exc) from exc
    message = await _persist_outbound(db, payload.to, payload.url, MessageMediaType.PDF)
    return SendResponse(message_id=message.id)


@router.post("/send-audio", response_model=SendResponse)
async def send_audio(payload: SendMediaRequest, db: DbSession, _: CurrentUser) -> SendResponse:
    try:
        await whatsapp_service.send_audio(_chat_id(payload.to), payload.url)
    except WhatsAppError as exc:
        raise _service_unavailable(exc) from exc
    message = await _persist_outbound(db, payload.to, payload.url, MessageMediaType.AUDIO)
    return SendResponse(message_id=message.id)


@router.post("/send-location", response_model=SendResponse)
async def send_location(payload: SendLocationRequest, db: DbSession, _: CurrentUser) -> SendResponse:
    try:
        await whatsapp_service.send_location(
            _chat_id(payload.to), payload.latitude, payload.longitude, payload.caption
        )
    except WhatsAppError as exc:
        raise _service_unavailable(exc) from exc
    message = await _persist_outbound(
        db, payload.to, f"{payload.latitude},{payload.longitude}", MessageMediaType.LOCATION
    )
    return SendResponse(message_id=message.id)
