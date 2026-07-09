from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class ChurchMember(Base, TimestampMixin):
    __tablename__ = "church_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    role: Mapped[str | None] = mapped_column(String(100))  # e.g. "louvor", "diácono"
    ministries: Mapped[list] = mapped_column(JSON, default=list)
    prayer_requests: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
