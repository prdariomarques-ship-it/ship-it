from sqlalchemy import JSON, String, Text
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
