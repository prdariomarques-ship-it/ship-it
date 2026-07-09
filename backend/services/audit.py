"""Persist structured audit/log entries to the logs table."""
from sqlalchemy.ext.asyncio import AsyncSession

from models.log import LogEntry


async def record_log(
    db: AsyncSession,
    source: str,
    message: str,
    level: str = "info",
    payload: dict | None = None,
) -> LogEntry:
    entry = LogEntry(source=source, message=message, level=level, payload=payload or {})
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry
