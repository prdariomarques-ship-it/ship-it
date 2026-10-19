"""Profile configuration (TOML) + environment. Fails loudly: a bad file stops the boot."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .domain import AlertRule, FilingsSpec, Instrument, MoversSpec, Profile, Section

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_KINDS = ("yahoo", "fx", "sgs", "focus", "gold_brl")
RESERVED = frozenset({"start", "ajuda", "help", "mercado", "cotacao", "altas", "fatos", "alertas"})


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    timezone: str
    profiles: tuple[Profile, ...]


def _instrument(raw: object, where: str) -> Instrument:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be a table")
    kind, symbol, name = raw.get("kind"), raw.get("symbol", ""), raw.get("name")
    if kind not in _KINDS:
        raise ConfigError(f"{where}.kind must be one of {_KINDS} (got {kind!r})")
    if not isinstance(symbol, str) or (not symbol.strip() and kind != "gold_brl"):
        raise ConfigError(f"{where}.symbol must be a non-empty string")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"{where}.name must be a non-empty string")
    decimals = raw.get("decimals", 2)
    if not isinstance(decimals, int) or isinstance(decimals, bool) or not 0 <= decimals <= 8:
        raise ConfigError(f"{where}.decimals must be an integer 0..8")
    return Instrument(kind=kind, symbol=symbol.strip(), name=name.strip(), unit=str(raw.get("unit", "")), decimals=decimals)


def _hhmm(value: object, where: str) -> str:
    if not isinstance(value, str) or not _HHMM.match(value):
        raise ConfigError(f"{where} must be \"HH:MM\"")
    return value


def _movers(raw: object, where: str) -> MoversSpec:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be a table")
    symbols = raw.get("symbols")
    if not isinstance(symbols, list) or not symbols or any(not isinstance(s, str) or not s.strip() for s in symbols):
        raise ConfigError(f"{where}.symbols must be a non-empty list of tickers")
    names = raw.get("names", {})
    if not isinstance(names, dict):
        raise ConfigError(f"{where}.names must be a table")
    top = raw.get("top", 5)
    if not isinstance(top, int) or isinstance(top, bool) or not 1 <= top <= 15:
        raise ConfigError(f"{where}.top must be an integer 1..15")
    seen: set[str] = set()
    universe = []
    for s in symbols:
        s = s.strip()
        if s in seen:
            raise ConfigError(f"{where}.symbols: {s!r} is duplicated")
        seen.add(s)
        universe.append(Instrument(kind="yahoo", symbol=s, name=str(names.get(s, s.removesuffix(".SA"))), unit="R$"))
    return MoversSpec(title=str(raw.get("title", "Maiores altas e quedas")), universe=tuple(universe), top_n=top)


def _filings(raw: object, where: str) -> FilingsSpec:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be a table")
    cats = raw.get("categories", ["Fato Relevante"])
    comps = raw.get("companies", [])
    if not isinstance(cats, list) or not cats or any(not isinstance(c, str) for c in cats):
        raise ConfigError(f"{where}.categories must be a non-empty list of strings")
    if not isinstance(comps, list) or any(not isinstance(c, str) or not c.strip() for c in comps):
        raise ConfigError(f"{where}.companies must be a list of strings")
    hours, mx = raw.get("window_hours", 24), raw.get("max_items", 8)
    if not isinstance(hours, int) or isinstance(hours, bool) or not 1 <= hours <= 168:
        raise ConfigError(f"{where}.window_hours must be an integer 1..168")
    if not isinstance(mx, int) or isinstance(mx, bool) or not 1 <= mx <= 30:
        raise ConfigError(f"{where}.max_items must be an integer 1..30")
    return FilingsSpec(categories=tuple(cats), companies=tuple(c.strip() for c in comps), window_hours=hours, max_items=mx)


def _alerts(raw: object, where: str, known: set[str]) -> tuple[AlertRule, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError(f"{where} must be a list")
    rules = []
    for n, a in enumerate(raw):
        w = f"{where}[{n}]"
        if not isinstance(a, dict):
            raise ConfigError(f"{w} must be a table")
        sym, thr = a.get("symbol"), a.get("min_abs_change_pct")
        if sym not in known:
            raise ConfigError(f"{w}.symbol {sym!r} is not an instrument of this profile")
        if isinstance(thr, bool) or not isinstance(thr, (int, float)) or not 0 < thr <= 100:
            raise ConfigError(f"{w}.min_abs_change_pct must be a number in (0, 100]")
        rules.append(AlertRule(symbol=sym, min_abs_change_pct=float(thr), label=str(a.get("label", ""))))
    return tuple(rules)


def parse(data: dict) -> Settings:
    tz = data.get("timezone", "America/Sao_Paulo")
    if not isinstance(tz, str):
        raise ConfigError("timezone must be a string")
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(tz)
    except Exception as exc:  # noqa: BLE001 - any failure to load the zone is a config error
        raise ConfigError(f"unknown timezone {tz!r}") from exc
    raw_profiles = data.get("profiles")
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise ConfigError("at least one [profiles.<id>] is required")
    profiles: list[Profile] = []
    for pid, p in raw_profiles.items():
        where = f"profiles.{pid}"
        if not _ID.match(pid):
            raise ConfigError(f"{where}: id must match {_ID.pattern}")
        if not isinstance(p, dict):
            raise ConfigError(f"{where} must be a table")
        schedule = p.get("schedule", [])
        if not isinstance(schedule, list):
            raise ConfigError(f"{where}.schedule must be a list of \"HH:MM\"")
        schedule = [_hhmm(s, f"{where}.schedule[]") for s in schedule]
        sections: list[Section] = []
        seen: set[str] = set()
        for sid, s in (p.get("sections") or {}).items():
            if not _ID.match(sid) or sid in seen or sid in RESERVED:
                raise ConfigError(f"{where}.sections: invalid, duplicated or reserved id {sid!r}")
            seen.add(sid)
            items = s.get("instruments") if isinstance(s, dict) else None
            if not isinstance(items, list) or not items:
                raise ConfigError(f"{where}.sections.{sid}.instruments must be a non-empty list")
            sections.append(Section(
                id=sid, title=str(s.get("title", sid)), note=str(s.get("note", "")),
                instruments=tuple(_instrument(i, f"{where}.sections.{sid}.instruments[{n}]") for n, i in enumerate(items)),
            ))
        if not sections:
            raise ConfigError(f"{where} needs at least one section")
        catchup = p.get("catchup_minutes", 30)
        if not isinstance(catchup, int) or isinstance(catchup, bool) or not 0 <= catchup <= 600:
            raise ConfigError(f"{where}.catchup_minutes must be an integer 0..600")
        interval = p.get("alert_interval_minutes", 15)
        if not isinstance(interval, int) or isinstance(interval, bool) or not 5 <= interval <= 240:
            raise ConfigError(f"{where}.alert_interval_minutes must be an integer 5..240")
        window = p.get("alert_window", ["10:00", "18:00"])
        if not isinstance(window, list) or len(window) != 2:
            raise ConfigError(f"{where}.alert_window must be [\"HH:MM\", \"HH:MM\"]")
        known = {i.symbol for sec in sections for i in sec.instruments}
        profiles.append(Profile(
            id=pid, title=str(p.get("title", pid)),
            token_env=str(p.get("token_env", f"MB_{pid.upper()}_BOT_TOKEN")),
            chat_env=str(p.get("chat_env", f"MB_{pid.upper()}_CHAT_ID")),
            schedule=tuple(schedule), weekdays_only=bool(p.get("weekdays_only", True)),
            sections=tuple(sections), catchup_minutes=catchup,
            movers=_movers(p["movers"], f"{where}.movers") if "movers" in p else None,
            filings=_filings(p["filings"], f"{where}.filings") if "filings" in p else None,
            alerts=_alerts(p.get("alerts"), f"{where}.alerts", known),
            alert_interval_minutes=interval,
            alert_window=(_hhmm(window[0], f"{where}.alert_window[0]"), _hhmm(window[1], f"{where}.alert_window[1]")),
        ))
    return Settings(timezone=tz, profiles=tuple(profiles))


def load(path: Path) -> Settings:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    return parse(data)
