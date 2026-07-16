from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class EmailAccount(Base, TimestampMixin):
    """A mailbox one User authorized the app to read (Sprint 1: Gmail,
    read-only). One row per (user, provider) — isolation between users is
    enforced by always looking this up from `ToolContext.user.id`, never
    from a mailbox address the model supplies (same principle as PROD-005
    for WhatsApp contacts)."""

    __tablename__ = "email_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_email_account_user_provider"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    email_address: Mapped[str] = mapped_column(String(255), nullable=False)
    # Encrypted with services.token_crypto (Fernet) — never stored in plaintext.
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
