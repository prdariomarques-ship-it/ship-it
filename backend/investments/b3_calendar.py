"""B3 pregão gate — same window the old Termux cron used (seg-sex, 10h-18h BRT)."""
from datetime import datetime
from zoneinfo import ZoneInfo

B3_TZ = ZoneInfo("America/Sao_Paulo")
B3_OPEN_HOUR = 10
B3_CLOSE_HOUR = 18


def is_pregao_now(now: datetime | None = None) -> bool:
    now = now.astimezone(B3_TZ) if now is not None else datetime.now(B3_TZ)
    return now.weekday() < 5 and B3_OPEN_HOUR <= now.hour < B3_CLOSE_HOUR
