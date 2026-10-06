"""Financial job queue — a table of its own (`financial_jobs`), isolated
from `jobs` (the WhatsApp/general queue). No shared code path, no shared
rows: a bug or load spike here cannot touch WhatsApp job claiming or
execution, and this worker never queries the `jobs` table.
"""
import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin, utcnow


class FinancialJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FinancialJob(Base, TimestampMixin):
    """Durable financial-monitor job: own table, own worker, own retry/backoff.

    `result` carries the outcome payload distinct from `status` — e.g. for
    telegram.send_message, {"delivered": true, "message_id": 123} vs
    {"delivered": false, "reason": "monitors_disabled"}. A job finishing
    SUCCEEDED means the handler ran without raising; it is never read as
    proof that a Telegram message was actually delivered — only
    result.delivered is.
    """

    __tablename__ = "financial_jobs"
    __table_args__ = (
        # At most one QUEUED-or-RUNNING row per job name at a time — the DB
        # itself refuses a second concurrent chain of the same monitor,
        # closing the query-then-insert race that app-level checks can't.
        # SQLAlchemy's Enum type persists the member NAME ("QUEUED"), not
        # `.value` ("queued") — verified against this project's existing
        # Job/JobStatus table before writing this condition.
        Index(
            "ix_financial_jobs_one_active_chain_per_name",
            "name",
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'RUNNING')"),
            sqlite_where=text("status IN ('QUEUED', 'RUNNING')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[FinancialJobStatus] = mapped_column(
        Enum(FinancialJobStatus), default=FinancialJobStatus.QUEUED, index=True
    )
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=3, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSON)
