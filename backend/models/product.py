"""Product catalog for the store domain (Oficina das Tintas / Marquescolor)."""

from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # e.g. "tinta_latex", "esmalte", "verniz", "acessorio" -- free string,
    # same convention as ChurchMember.role: the catalog grows faster than a
    # DB enum should be migrated.
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    # e.g. "lata_18L", "galao_3.6L", "un"
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="un")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
