from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class StoreCustomer(Base, TimestampMixin):
    __tablename__ = "store_customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    orders: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    # Qualificação comercial: "pintor", "lojista" ou "consumidor_final".
    # Mesma convenção de ChurchMember.role -- string livre, validada em
    # código (agents/tools/domain.py::_VALID_SEGMENTS), não enum de banco.
    segment: Mapped[str | None] = mapped_column(String(50), index=True)


class StoreQuote(Base, TimestampMixin):
    __tablename__ = "store_quotes"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("store_customers.id"), index=True
    )
    items: Mapped[list] = mapped_column(JSON, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    order_result: Mapped[dict | None] = mapped_column(JSON)
