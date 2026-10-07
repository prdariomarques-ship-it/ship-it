"""yahoo_finance: basis-point-safe delta math, staleness, and the explicit
age-disclosure line every monitor message must carry when data isn't
fresh enough to present as current (the review's point: tolerating a few
days of old data as "not broken" is not the same claim as "this is now")."""
from datetime import datetime, timedelta, timezone

import pytest

from investments.yahoo_finance import (
    FRESH_ENOUGH_HOURS,
    PriceSeries,
    STALE_AFTER_SECONDS,
    age_disclosure,
)


def test_age_disclosure_empty_when_fresh():
    assert age_disclosure(1.0) == ""
    assert age_disclosure(FRESH_ENOUGH_HOURS) == ""


def test_age_disclosure_warns_past_threshold():
    line = age_disclosure(FRESH_ENOUGH_HOURS + 0.1)
    assert line != ""
    assert "pregão de hoje não confirmado" in line


def test_age_disclosure_states_the_actual_age():
    line = age_disclosure(72.0)
    assert "72h" in line


def test_price_series_age_seconds():
    now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    series = PriceSeries(closes=[1.0, 2.0], timestamps=[int((now - timedelta(hours=5)).timestamp()), int(now.timestamp()) - 3600])
    assert series.age_seconds(now) == pytest.approx(3600, abs=1)


def test_stale_after_seconds_is_four_days():
    assert STALE_AFTER_SECONDS == 4 * 24 * 3600
