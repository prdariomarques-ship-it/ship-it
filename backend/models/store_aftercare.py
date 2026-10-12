from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class StoreDelivery(Base, TimestampMixin):
    __tablename__ = "store_deliveries"
    __table_args__ = (UniqueConstraint("customer_id", "order_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("store_customers.id"))
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True)
    order_id: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(32))
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    followup_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[str | None] = mapped_column(Text)
    confirmed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class StoreSupportCase(Base, TimestampMixin):
    __tablename__ = "store_support_cases"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True)
    source_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"), unique=True
    )
    subject: Mapped[str] = mapped_column(String(160))
    report: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="open")
    resolution: Mapped[str | None] = mapped_column(Text)
