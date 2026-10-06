"""B3 pregão gate — same window the old Termux cron used (seg-sex, 10h-18h BRT).

Known, unsolved gap: this checks weekday + hour only — it has no B3
holiday calendar, and no calendar for any of the US/European/Asian
exchanges the daily briefing also quotes. A B3 holiday that happens to
fall on a US/European trading day (or vice versa) is not detected here;
yahoo_finance.StaleDataError is a backstop for the resulting stale quote,
but it can't distinguish "market closed for a holiday" from "the data
feed is actually broken" — both just look stale. Do not read a passing
is_pregao_now() as proof any specific market is actually open today.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

B3_TZ = ZoneInfo("America/Sao_Paulo")
B3_OPEN_HOUR = 10
B3_CLOSE_HOUR = 18


def is_pregao_now(now: datetime | None = None) -> bool:
    now = now.astimezone(B3_TZ) if now is not None else datetime.now(B3_TZ)
    return now.weekday() < 5 and B3_OPEN_HOUR <= now.hour < B3_CLOSE_HOUR
