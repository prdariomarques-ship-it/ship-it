"""Pure schedule arithmetic. Same lesson as the DARIUS scheduler: one run per slot, no burst after downtime."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def _slot_dt(day: date, hhmm: str, tz: ZoneInfo) -> datetime:
    h, m = hhmm.split(":")
    return datetime.combine(day, time(int(h), int(m)), tzinfo=tz)


def due_slot(now: datetime, schedule: tuple[str, ...], weekdays_only: bool, catchup_minutes: int,
             last_slot: str | None, tz: ZoneInfo) -> str | None:
    """The slot (ISO local string) to run now, or None.

    Only the LATEST slot at or before `now` is considered, and only within `catchup_minutes` of it: after a long
    outage the bot resumes on the next slot instead of sending a pile of stale bulletins. A slot already recorded in
    `last_slot` (or older) never fires again, so a restart inside the window cannot duplicate it.
    """
    local = now.astimezone(tz)
    if weekdays_only and local.weekday() >= 5:
        return None
    candidates = [_slot_dt(local.date(), s, tz) for s in schedule]
    past = [c for c in candidates if c <= local]
    if not past:
        return None
    slot = max(past)
    if local - slot > timedelta(minutes=catchup_minutes):
        return None
    iso = slot.isoformat(timespec="minutes")
    if last_slot is not None and iso <= last_slot:
        return None
    return iso


def in_window(now: datetime, window: tuple[str, str], weekdays_only: bool, tz: ZoneInfo) -> bool:
    local = now.astimezone(tz)
    if weekdays_only and local.weekday() >= 5:
        return False
    start, end = _slot_dt(local.date(), window[0], tz), _slot_dt(local.date(), window[1], tz)
    return start <= local <= end
