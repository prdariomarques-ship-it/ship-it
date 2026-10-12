"""Registro de cada resposta por voz do vendedor da loja: o que foi falado, o que aconteceu e por quê.

Uma linha por tentativa lógica (chave de deduplicação única). Estados:
queued -> generating -> sending -> sent
                     \\-> cancelled            (cliente respondeu, humano assumiu, pausa, opt-out, mensagem velha...)
                     \\-> failed_before_send   (geração falhou/formato inválido; ou transporte provadamente não enviou)
                      sending -> needs_review  (resultado do envio INCERTO: nunca reenviar nem mandar texto de reserva)
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin

VOICE_STATUSES = ("queued", "generating", "sending", "sent", "cancelled", "failed_before_send", "needs_review")


class StoreVoiceSend(Base, TimestampMixin):
    __tablename__ = "store_voice_sends"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # reply | followup
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True, nullable=False)
    instance: Mapped[str] = mapped_column(String(64), nullable=False)
    source_message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), index=True)
    followup_id: Mapped[int | None] = mapped_column(Integer, index=True)  # store_followups.id (sem FK: tabela opcional)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    script_text: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audio_sha256: Mapped[str | None] = mapped_column(String(64))
    audio_seconds: Mapped[float | None] = mapped_column(Float)
    audio_bytes: Mapped[int | None] = mapped_column(Integer)
    engine: Mapped[str | None] = mapped_column(String(32))
    model_revision: Mapped[str | None] = mapped_column(String(64))
    reference_sha256: Mapped[str | None] = mapped_column(String(64))
    receipt_id: Mapped[str | None] = mapped_column(String(128))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
