"""Outbound WhatsApp endpoints (text, image, PDF/file, audio, location).

All sends go through the configured provider (Strategy) and every outbound
message is persisted and fed into the contact memory.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import CurrentUser
from auth.permissions import require_admin
from database.session import get_db
from models.message import MessageMediaType
from models.user import User
from providers.whatsapp.base import WhatsAppProviderError
from providers.whatsapp.factory import get_whatsapp_provider
from services.messaging import persist_outbound_message

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


def _bad_gateway(exc: WhatsAppProviderError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.post("/send-text", response_model=SendResponse)
async def send_text(
    payload: SendTextRequest, db: DbSession, _: CurrentUser
) -> SendResponse:
    try:
        await get_whatsapp_provider().send_text(payload.to, payload.content)
    except WhatsAppProviderError as exc:
        raise _bad_gateway(exc) from exc
    message = await persist_outbound_message(
        db, payload.to, payload.content, MessageMediaType.TEXT
    )
    return SendResponse(message_id=message.id)


@router.post("/send-image", response_model=SendResponse)
async def send_image(
    payload: SendMediaRequest, db: DbSession, _: CurrentUser
) -> SendResponse:
    try:
        await get_whatsapp_provider().send_image(
            payload.to, payload.url, payload.filename, payload.caption
        )
    except WhatsAppProviderError as exc:
        raise _bad_gateway(exc) from exc
    message = await persist_outbound_message(
        db, payload.to, payload.url, MessageMediaType.IMAGE
    )
    return SendResponse(message_id=message.id)


@router.post("/send-file", response_model=SendResponse)
async def send_file(
    payload: SendMediaRequest, db: DbSession, _: CurrentUser
) -> SendResponse:
    try:
        await get_whatsapp_provider().send_file(
            payload.to, payload.url, payload.filename, payload.caption
        )
    except WhatsAppProviderError as exc:
        raise _bad_gateway(exc) from exc
    message = await persist_outbound_message(
        db, payload.to, payload.url, MessageMediaType.PDF
    )
    return SendResponse(message_id=message.id)


@router.post("/send-audio", response_model=SendResponse)
async def send_audio(
    payload: SendMediaRequest, db: DbSession, _: CurrentUser
) -> SendResponse:
    try:
        await get_whatsapp_provider().send_audio(payload.to, payload.url)
    except WhatsAppProviderError as exc:
        raise _bad_gateway(exc) from exc
    message = await persist_outbound_message(
        db, payload.to, payload.url, MessageMediaType.AUDIO
    )
    return SendResponse(message_id=message.id)


@router.post("/send-location", response_model=SendResponse)
async def send_location(
    payload: SendLocationRequest, db: DbSession, _: CurrentUser
) -> SendResponse:
    try:
        await get_whatsapp_provider().send_location(
            payload.to, payload.latitude, payload.longitude, payload.caption
        )
    except WhatsAppProviderError as exc:
        raise _bad_gateway(exc) from exc
    message = await persist_outbound_message(
        db,
        payload.to,
        f"{payload.latitude},{payload.longitude}",
        MessageMediaType.LOCATION,
    )
    return SendResponse(message_id=message.id)


# ---------------------------------------------------------------------------------------------------------------------
# Revisão de entregas INCERTAS (needs_review) — somente administrador.
#
# Um envio cujo resultado ficou incerto nunca é reenviado automaticamente. Aqui o administrador (a) inspeciona a reserva e (b) ACEITA a
# incerteza: fecha a reserva como `closed_unknown` e pausa a conversa. Isto NÃO reenvia, NÃO atribui recibo e NÃO afirma entrega ou
# não entrega. O ator vem SEMPRE da autenticação (o cliente não informa ator, recibo nem resultado), o escopo da conversa
# (contato + instância) e a revisão esperada são explícitos, e a decisão, a pausa e a auditoria são confirmadas numa única transação.
# ---------------------------------------------------------------------------------------------------------------------
_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,254}$"   # sem '/', sem espaços: não vira caminho nem consulta parcial


class CloseUnknownRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")              # receipt_id, actor_id, status etc. do cliente são recusados (422)

    contact_id: StrictInt = Field(gt=0)
    instance: str = Field(min_length=1, max_length=255)
    kind: str = Field(pattern=r"^(send|alert)$")
    key: str = Field(pattern=_KEY_PATTERN)
    expected_revision: StrictInt = Field(ge=0)             # inteiro de verdade: True, "1" e 1.0 são recusados
    reason: str = Field(min_length=1, max_length=500)
    no_resend_confirmation: StrictBool                     # precisa ser o booleano true: "true", 1 e null são recusados

    @field_validator("instance")
    @classmethod
    def _instance_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("instance must not be blank")
        return value

    @field_validator("reason")
    @classmethod
    def _reason_substantive(cls, value: str) -> str:
        if len("".join(value.split())) < 8:
            raise ValueError("reason needs at least 8 non-whitespace characters")
        return value

    @field_validator("no_resend_confirmation")
    @classmethod
    def _must_confirm(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("no_resend_confirmation must be true: closing never resends")
        return value


@router.get("/deliveries")
async def inspect_conversation_delivery(
    db: DbSession,
    _: Annotated[User, Depends(require_admin)],
    contact_id: Annotated[int, Query(gt=0)],
    instance: Annotated[str, Query(min_length=1, max_length=255)],
    kind: Annotated[str, Query(pattern=r"^(send|alert)$")],
    key: Annotated[str, Query(pattern=_KEY_PATTERN)],
) -> dict:
    """Metadados de UMA reserva, no escopo (contato, instância). Reserva de outro escopo responde 404 igual à inexistente."""
    from services import conversation_control

    result = await conversation_control.inspect_delivery(db, contact_id, instance, kind, key)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="delivery intent not found")
    return result


@router.post("/deliveries/close-unknown")
async def close_unknown_delivery(
    payload: CloseUnknownRequest, db: DbSession, admin: Annotated[User, Depends(require_admin)],
) -> dict:
    from services import conversation_control

    try:
        result = await conversation_control.close_unknown(
            db, payload.contact_id, payload.instance, payload.kind, payload.key, payload.expected_revision,
            int(admin.id), payload.reason,
        )
    except conversation_control.ControlConflict as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()                                       # intenção + pausa + auditoria: uma única transação
    return result
