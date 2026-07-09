from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class LogEntry(Base, TimestampMixin):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(20), default="info", index=True)
    source: Mapped[str] = mapped_column(String(100), index=True)  # e.g. "webhook", "agent:personal"
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
