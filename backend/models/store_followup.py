"""Acompanhamento comercial proativo (retomada de orçamento, sugestão de reposição) do vendedor da loja.

Cada linha tem: cliente e instância, motivo e registro de origem, horário previsto, estado, limite de tentativas,
motivo de cancelamento, chave que impede duplicidade e histórico do resultado.
Estados: scheduled -> queued (job de envio criado) -> sent | needs_review ;  scheduled -> cancelled ;  scheduled -> exhausted.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin

FOLLOWUP_STATUSES = ("scheduled", "queued", "sent", "needs_review", "cancelled", "exhausted")
FOLLOWUP_KINDS = ("quote_resume", "restock")


class StoreFollowup(Base, TimestampMixin):
    __tablename__ = "store_followups"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("store_customers.id"), index=True, nullable=False)
    instance: Mapped[str] = mapped_column(String(64), nullable=False)
    origin_type: Mapped[str] = mapped_column(String(32), nullable=False)  # store_quote | store_customer_orders
    origin_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="scheduled")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # fatos verificáveis usados no texto
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[int | None] = mapped_column(Integer)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
