from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class Embedding(Base, TimestampMixin):
    """Metadata for a vector stored in Qdrant (the vector itself lives there)."""

    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    source: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g. "whatsapp", "note"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    vector_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )  # Qdrant point id
