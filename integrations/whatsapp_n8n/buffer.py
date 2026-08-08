"""
SQLite message buffer with deduplication for WhatsApp → n8n pipeline.

Responsibilities:
  - Store incoming messages keyed by Evolution API's message_id (PRIMARY KEY).
  - Reject duplicates silently (UNIQUE constraint).
  - Provide a time-windowed flush that returns only unprocessed messages.
  - Log every flush for audit.
  - Expose stats (pending / total / last flush).

No external dependencies beyond the Python stdlib.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator

# ---------------------------------------------------------------------------
# Config (all overridable via environment variables)
# ---------------------------------------------------------------------------

BUFFER_DB_PATH: str = os.getenv("BUFFER_DB_PATH", "./whatsapp_buffer.db")
BUFFER_WINDOW_HOURS: float = float(os.getenv("BUFFER_WINDOW_HOURS", "8"))

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS messages (
    msg_id       TEXT PRIMARY KEY,
    sender       TEXT NOT NULL,
    sender_phone TEXT NOT NULL,
    text         TEXT NOT NULL,
    received_at  TEXT NOT NULL,       -- ISO-8601, UTC
    msg_type     TEXT NOT NULL DEFAULT 'text',  -- 'text' | 'audio_transcript'
    processed    INTEGER NOT NULL DEFAULT 0,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS flush_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    flushed_at   TEXT NOT NULL,
    msg_count    INTEGER NOT NULL,
    window_hours REAL NOT NULL,
    trigger      TEXT NOT NULL        -- 'schedule' | 'manual' | 'api'
);
"""

# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

@contextmanager
def _conn(db_path: str = BUFFER_DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """Yield a committed, auto-closed SQLite connection."""
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db(db_path: str = BUFFER_DB_PATH) -> None:
    """Create tables on first use (idempotent)."""
    with _conn(db_path) as con:
        con.executescript(_DDL)


def make_fallback_id(sender_phone: str, text: str, timestamp_seconds: int) -> str:
    """Stable dedup key when the provider sends no unique message ID."""
    raw = f"{sender_phone}|{text[:200]}|{timestamp_seconds}"
    return "hash-" + hashlib.sha256(raw.encode()).hexdigest()[:20]


def add_message(
    *,
    msg_id: str,
    sender: str,
    sender_phone: str,
    text: str,
    received_at: str,
    msg_type: str = "text",
    db_path: str = BUFFER_DB_PATH,
) -> bool:
    """
    Insert a message into the buffer.

    Returns True if inserted, False if the msg_id already exists (duplicate).
    Callers should log the False case for observability but treat it as
    normal operation.
    """
    with _conn(db_path) as con:
        try:
            con.execute(
                """INSERT INTO messages
                       (msg_id, sender, sender_phone, text, received_at, msg_type)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (msg_id, sender, sender_phone, text, received_at, msg_type),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def get_pending(
    window_hours: float = BUFFER_WINDOW_HOURS,
    db_path: str = BUFFER_DB_PATH,
) -> list[dict]:
    """
    Return all unprocessed messages that arrived within the last `window_hours`.

    Messages older than the window are left in the DB (processed=0) but not
    returned — they're considered stale and will be skipped in future flushes
    too (a manual cleanup command handles those separately).
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=window_hours)
    ).isoformat()
    with _conn(db_path) as con:
        rows = con.execute(
            """SELECT msg_id, sender, sender_phone, text, received_at, msg_type
               FROM   messages
               WHERE  processed = 0
               AND    received_at >= ?
               ORDER  BY received_at ASC""",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_processed(msg_ids: list[str], db_path: str = BUFFER_DB_PATH) -> None:
    """Atomically mark a batch of message IDs as processed."""
    if not msg_ids:
        return
    now = datetime.now(timezone.utc).isoformat()
    with _conn(db_path) as con:
        con.executemany(
            "UPDATE messages SET processed = 1, processed_at = ? WHERE msg_id = ?",
            [(now, mid) for mid in msg_ids],
        )


def log_flush(
    msg_count: int,
    window_hours: float,
    trigger: str,
    db_path: str = BUFFER_DB_PATH,
) -> None:
    """Record a flush event (for auditing / dashboards)."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn(db_path) as con:
        con.execute(
            """INSERT INTO flush_log (flushed_at, msg_count, window_hours, trigger)
               VALUES (?, ?, ?, ?)""",
            (now, msg_count, window_hours, trigger),
        )


def purge_processed(older_than_days: int = 30, db_path: str = BUFFER_DB_PATH) -> int:
    """Delete already-processed messages older than N days. Returns row count."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=older_than_days)
    ).isoformat()
    with _conn(db_path) as con:
        cur = con.execute(
            "DELETE FROM messages WHERE processed = 1 AND processed_at < ?",
            (cutoff,),
        )
        return cur.rowcount


def get_stats(db_path: str = BUFFER_DB_PATH) -> dict:
    """Return a snapshot of buffer health."""
    with _conn(db_path) as con:
        total = con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        pending = con.execute(
            "SELECT COUNT(*) FROM messages WHERE processed = 0"
        ).fetchone()[0]
        last_row = con.execute(
            """SELECT flushed_at, msg_count, trigger
               FROM   flush_log
               ORDER  BY id DESC
               LIMIT  1"""
        ).fetchone()
    return {
        "total_messages": total,
        "pending_messages": pending,
        "processed_messages": total - pending,
        "last_flush": dict(last_row) if last_row else None,
    }
