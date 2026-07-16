from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class GoogleCalendarAccount(Base, TimestampMixin):
    """A Google Calendar one User authorized the app to read/write (Sprint
    2). One row per (user, provider) — isolation between users is enforced
    by always looking this up from `ToolContext.user.id`, never from a
    calendar id the model supplies (same principle as PROD-005 for WhatsApp
    contacts, and Sprint 1 for Gmail)."""

    __tablename__ = "google_calendar_accounts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", name="uq_gcalendar_account_user_provider"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    account_label: Mapped[str] = mapped_column(String(255), nullable=False)
    # Encrypted with services.token_crypto (Fernet) — never stored in plaintext.
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
