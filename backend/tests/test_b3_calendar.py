"""B3 holiday calendar: the Easter-anchored moving holidays (Carnaval,
Sexta-feira Santa, Corpus Christi) are computed, not looked up from a
static table — these tests check the computation against known, publicly
published B3/ANBIMA dates across several different years, not just one,
since an off-by-one in the Easter algorithm would otherwise only show up
in whichever single year a lookup table happened to hardcode."""
from datetime import date

import pytest

from investments.b3_calendar import _easter_sunday, b3_holidays, is_b3_holiday


@pytest.mark.parametrize(
    "year,expected",
    [
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
    ],
)
def test_easter_sunday_matches_published_dates(year, expected):
    assert _easter_sunday(year) == expected


@pytest.mark.parametrize(
    "year,carnaval_monday,carnaval_tuesday,good_friday,corpus_christi",
    [
        (2024, date(2024, 2, 12), date(2024, 2, 13), date(2024, 3, 29), date(2024, 5, 30)),
        (2025, date(2025, 3, 3), date(2025, 3, 4), date(2025, 4, 18), date(2025, 6, 19)),
        (2026, date(2026, 2, 16), date(2026, 2, 17), date(2026, 4, 3), date(2026, 6, 4)),
    ],
)
def test_moving_holidays_match_published_b3_calendar(
    year, carnaval_monday, carnaval_tuesday, good_friday, corpus_christi
):
    holidays = b3_holidays(year)
    assert carnaval_monday in holidays
    assert carnaval_tuesday in holidays
    assert good_friday in holidays
    assert corpus_christi in holidays


def test_fixed_date_holidays_present_every_year():
    holidays = b3_holidays(2026)
    assert date(2026, 1, 1) in holidays
    assert date(2026, 4, 21) in holidays
    assert date(2026, 5, 1) in holidays
    assert date(2026, 9, 7) in holidays
    assert date(2026, 10, 12) in holidays
    assert date(2026, 11, 2) in holidays
    assert date(2026, 11, 15) in holidays
    assert date(2026, 11, 20) in holidays
    assert date(2026, 12, 25) in holidays


def test_an_ordinary_trading_day_is_not_a_holiday():
    assert is_b3_holiday(date(2026, 10, 6)) is False  # a plain Tuesday


def test_is_b3_holiday_matches_the_set():
    assert is_b3_holiday(date(2026, 9, 7)) is True
