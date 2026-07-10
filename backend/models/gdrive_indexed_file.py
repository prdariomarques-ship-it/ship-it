from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class GoogleDriveIndexedFile(Base, TimestampMixin):
    """Bookkeeping for one Google Drive file a user has indexed into the
    Knowledge Store — not the knowledge itself (that lives in Qdrant, via
    the existing Memory Manager/`Embedding` table, untouched in shape).

    This table only tracks: which file, what it was named/modified-at when
    last indexed, and which `Embedding.id`s its chunks produced —  enough
    to (a) skip re-indexing an unchanged file and (b) delete its stale
    chunks (`MemoryManager.forget`) when the file *has* changed, so
    "atualizar índice" replaces content instead of accumulating duplicates.
    """

    __tablename__ = "google_drive_indexed_files"
    __table_args__ = (UniqueConstraint("user_id", "file_id", name="uq_gdrive_indexed_file_user_file"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    modified_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Embedding.id list (Postgres PKs, not Qdrant point ids) — passed straight
    # to MemoryManager.forget() when this file needs re-indexing.
    embedding_ids: Mapped[list] = mapped_column(JSON, default=list)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
