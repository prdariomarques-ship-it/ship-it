"""FAKE record_log -- records calls for inspection instead of writing to
a real `logs` table (the real services/audit.py + models/log.py were
read from the production container for verification, not supplied as
source files for this delivery)."""

RECORD_LOG_CALLS: list[dict] = []


async def record_log(db, source, message, level="info", payload=None):
    RECORD_LOG_CALLS.append({"source": source, "message": message, "level": level, "payload": payload or {}})
