"""Persisted overrides for a small, explicit set of admin-editable runtime
settings (see `services/app_settings.py::SETTINGS_CATALOG`) — everything
else in `utils.config.Settings` stays purely `.env`-sourced. A row only
ever exists for a setting an admin has actually changed via the dashboard;
its absence just means "still at the `.env` default", not an error."""

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False)
    editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
