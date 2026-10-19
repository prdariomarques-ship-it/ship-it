"""Link between one inbound WhatsApp message and the DARIUS task created for it.

The row is the Dario OS side of the end-to-end audit trail
(message -> DARIUS task -> authorized execution -> reply sent). It is also the
local dedup barrier: `dedupe_key` (instance + provider message id) is UNIQUE and
doubles as the DARIUS `Idempotency-Key`, so a duplicated webhook/job, a retry
after a timeout, or a crash between "task created" and "task id stored" can
never produce a second task or a second reply.

It never stores message text or the reply text -- only ids, sizes and a hash --
so the audit trail carries no conversation content.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin

SUBMITTING = "submitting"        # row claimed, DARIUS task not confirmed yet (retryable)
SUBMITTED = "submitted"          # DARIUS task exists; waiting for its result
REPLY_QUEUED = "reply_queued"    # DARIUS completed; the reply was handed to whatsapp.send_text
FAILED = "failed"                # permanent failure (DARIUS failed/rejected/empty result/credential)
CANCELLED = "cancelled"          # DARIUS task cancelled or rejected by an operator
EXPIRED = "expired"              # no result inside the reply window; nothing is sent late
SKIPPED = "skipped"              # DARIUS not configured; nothing was attempted

TERMINAL = frozenset({REPLY_QUEUED, FAILED, CANCELLED, EXPIRED, SKIPPED})


class DariusWhatsAppTask(Base, TimestampMixin):
    __tablename__ = "darius_whatsapp_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), nullable=False, index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), nullable=False, index=True)
    instance: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SUBMITTING, index=True)
    darius_task_id: Mapped[str | None] = mapped_column(String(128))
    darius_status: Mapped[str | None] = mapped_column(String(16))
    control_revision: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    reply_job_id: Mapped[int | None] = mapped_column(Integer)
    reply_chars: Mapped[int | None] = mapped_column(Integer)
    reply_sha256: Mapped[str | None] = mapped_column(String(64))
    history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_darius_whatsapp_tasks_status_created", "status", "created_at"),)
