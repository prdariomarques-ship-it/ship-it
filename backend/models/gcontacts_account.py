from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class GoogleContactsAccount(Base, TimestampMixin):
    """A Google Contacts (People API) address book one User authorized the
    app to read/write (Sprint 2). One row per (user, provider) — same
    isolation principle as `GoogleCalendarAccount`/`EmailAccount`: always
    resolved from `ToolContext.user.id`, never from an id the model
    supplies.

    Deliberately unrelated to `models.contact.Contact`, which is Dario OS's
    own WhatsApp-conversation contact book — see `docs/CONTACTS.md`."""

    __tablename__ = "google_contacts_accounts"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_gcontacts_account_user_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    account_label: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
