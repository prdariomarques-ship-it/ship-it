"""B3 pregão gate — weekday + trading-hour window (seg-sex, 10h-18h BRT,
same as the old Termux cron) AND the official national/ANBIMA holiday
calendar B3 observes.

Holidays are computed, not looked up from a static table that would go
stale: fixed-date national holidays plus the Easter-anchored moving ones
(Carnaval, Sexta-feira Santa, Corpus Christi), via the standard Gregorian
Easter algorithm. This covers every year, not just a hardcoded range.

Known, disclosed gaps (still unsolved, narrower than before this file
existed but not closed):
  - No calendar for the US/European/Asian exchanges the daily briefing
    also quotes — a B3 holiday that happens to fall on a US trading day
    (or vice versa) is still not detected for those tickers.
  - B3's Dec 24 / Dec 31 REDUCED-HOUR sessions (not full closures) are
    not modeled — treated as ordinary trading days here, which is correct
    for "is the market open at all" but not for "at full/normal hours".
  - An ad hoc, decreed closure (a one-off national day of mourning, a
    rare extraordinary B3 closure) is not and cannot be predicted by a
    computed calendar; only a real B3/ANBIMA feed could catch that.
yahoo_finance.StaleDataError remains the hard backstop for the resulting
stale quote in either gap case — it can't tell "known holiday" from "feed
is broken", but it still blocks presenting old data as current.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

B3_TZ = ZoneInfo("America/Sao_Paulo")
B3_OPEN_HOUR = 10
B3_CLOSE_HOUR = 18


def _easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm (Meeus/Jones/Butcher) — exact for any
    Gregorian-calendar year, not an approximation or a lookup table."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def b3_holidays(year: int) -> frozenset[date]:
    """The B3/ANBIMA national holiday calendar for a given year. Carnaval
    is two days (Monday + Tuesday); B3 is also closed Ash Wednesday
    afternoon in practice, but that's a half-day, not modeled here (see
    module docstring's Dec 24/31 note — same category of gap)."""
    easter = _easter_sunday(year)
    carnaval_monday = easter - timedelta(days=48)
    carnaval_tuesday = easter - timedelta(days=47)
    good_friday = easter - timedelta(days=2)
    corpus_christi = easter + timedelta(days=60)
    return frozenset(
        {
            date(year, 1, 1),  # Ano Novo
            carnaval_monday,
            carnaval_tuesday,
            good_friday,  # Sexta-feira Santa
            date(year, 4, 21),  # Tiradentes
            date(year, 5, 1),  # Dia do Trabalho
            corpus_christi,
            date(year, 9, 7),  # Independência
            date(year, 10, 12),  # Nossa Senhora Aparecida
            date(year, 11, 2),  # Finados
            date(year, 11, 15),  # Proclamação da República
            date(year, 11, 20),  # Consciência Negra (observado pela B3)
            date(year, 12, 25),  # Natal
        }
    )


def is_b3_holiday(day: date) -> bool:
    return day in b3_holidays(day.year)


def is_pregao_now(now: datetime | None = None) -> bool:
    now = now.astimezone(B3_TZ) if now is not None else datetime.now(B3_TZ)
    if now.weekday() >= 5 or not (B3_OPEN_HOUR <= now.hour < B3_CLOSE_HOUR):
        return False
    return not is_b3_holiday(now.date())
