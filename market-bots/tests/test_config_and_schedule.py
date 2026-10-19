from __future__ import annotations

from pathlib import Path

import pytest

from market_bots import config
from market_bots.schedule import due_slot, in_window

from .conftest import TZ, local

ROOT = Path(__file__).resolve().parents[1]
MINIMAL = {
    "profiles": {"p": {"schedule": ["10:00"], "sections": {"s": {"instruments": [
        {"kind": "yahoo", "symbol": "^BVSP", "name": "Ibov"}]}}}}
}


def test_shipped_profiles_load_and_have_both_bots():
    settings = config.load(ROOT / "profiles.toml")
    assert {p.id for p in settings.profiles} == {"national", "global"}
    nat = next(p for p in settings.profiles if p.id == "national")
    glob = next(p for p in settings.profiles if p.id == "global")
    assert nat.movers and len(nat.movers.universe) >= 50 and nat.filings and nat.alerts
    assert {s.id for s in nat.sections} >= {"indices", "cambio", "ouro", "juros"}
    # the global bot covers every region the user asked for
    assert {s.id for s in glob.sections} >= {"asia", "europa", "eua", "americas", "macro"}
    symbols = {i.symbol for s in glob.sections for i in s.instruments}
    assert {"^N225", "^FTSE", "^GSPC", "^BVSP", "^MXX", "GC=F", "SPCX"} <= symbols


def test_every_alert_symbol_exists_in_its_profile():
    for p in config.load(ROOT / "profiles.toml").profiles:
        known = {i.symbol for s in p.sections for i in s.instruments}
        assert all(a.symbol in known for a in p.alerts)


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d["profiles"]["p"].update(schedule=["25:00"]), "HH:MM"),
    (lambda d: d["profiles"]["p"]["sections"]["s"]["instruments"][0].update(kind="nope"), "kind"),
    (lambda d: d["profiles"]["p"]["sections"].update(mercado={"instruments": [
        {"kind": "yahoo", "symbol": "X", "name": "x"}]}), "reserved"),
    (lambda d: d["profiles"]["p"].update(alerts=[{"symbol": "NOPE", "min_abs_change_pct": 1}]), "not an instrument"),
    (lambda d: d["profiles"]["p"].update(alerts=[{"symbol": "^BVSP", "min_abs_change_pct": 0}]), "min_abs_change_pct"),
    (lambda d: d.update(timezone="Mars/Olympus"), "timezone"),
    (lambda d: d["profiles"]["p"].update(catchup_minutes=-1), "catchup"),
])
def test_invalid_config_is_refused(mutate, needle):
    import copy

    data = copy.deepcopy(MINIMAL)
    mutate(data)
    with pytest.raises(config.ConfigError, match=needle):
        config.parse(data)


def test_due_slot_fires_once_per_slot_and_not_on_weekends():
    sched = ("10:20", "18:20")
    mon = lambda h, m: local(2026, 10, 19, h, m)   # a Monday
    assert due_slot(mon(10, 19), sched, True, 30, None, TZ) is None            # before the slot
    first = due_slot(mon(10, 21), sched, True, 30, None, TZ)
    assert first and first.startswith("2026-10-19T10:20")
    assert due_slot(mon(10, 22), sched, True, 30, first, TZ) is None            # already done: a restart cannot repeat it
    assert due_slot(mon(10, 55), sched, True, 30, None, TZ) is None             # outside the catch-up window: skipped
    second = due_slot(mon(18, 25), sched, True, 30, first, TZ)
    assert second and second.startswith("2026-10-19T18:20")
    assert due_slot(local(2026, 10, 17, 10, 25), sched, True, 30, None, TZ) is None   # Saturday


def test_no_burst_after_long_downtime():
    # bot was down all morning, comes back at 15:00: neither 10:20 nor an old slot is replayed
    assert due_slot(local(2026, 10, 19, 15, 0), ("10:20", "18:20"), True, 30, None, TZ) is None


def test_alert_window_respects_weekday_and_hours():
    w = ("10:00", "18:00")
    assert in_window(local(2026, 10, 19, 12, 0), w, True, TZ)
    assert not in_window(local(2026, 10, 19, 9, 59), w, True, TZ)
    assert not in_window(local(2026, 10, 19, 18, 1), w, True, TZ)
    assert not in_window(local(2026, 10, 17, 12, 0), w, True, TZ)
