"""Horário de atendimento da LOJA: única fonte para (a) o agente responder "que horas vocês abrem?" e (b) a janela dos contatos proativos.

Os horários vêm de configuração (`STORE_HOURS`), informados pelo proprietário em 12/10/2026 e **a confirmar com a equipe da
loja**: segunda a sexta 08:30–17:30; sábado 08:30–12:30; feriados 08:30–12:30. **Domingo não foi informado**: é tratado como
"sem atendimento informado" (nada é prometido ao cliente e nenhum contato proativo sai), mesmo que seja feriado.

Feriados: nacionais fixos + Sexta-feira Santa (calculada). Carnaval, Corpus Christi e feriados MUNICIPAIS/ESTADUAIS não são
presumidos: entram por `STORE_EXTRA_HOLIDAYS` (datas ISO separadas por vírgula); `STORE_EXCLUDED_HOLIDAYS` remove algum dos
presumidos. Feriado prevalece sobre o dia da semana (segunda a sábado). Fuso: `STORE_TIMEZONE` (America/Sao_Paulo).
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from utils.config import Settings

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_NAMES_PT = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
_FIXED = {
    (1, 1): "Confraternização Universal", (4, 21): "Tiradentes", (5, 1): "Dia do Trabalho", (9, 7): "Independência do Brasil",
    (10, 12): "Nossa Senhora Aparecida", (11, 2): "Finados", (11, 15): "Proclamação da República", (11, 20): "Consciência Negra",
    (12, 25): "Natal",
}


class StoreHoursError(ValueError):
    """Configuração de horário inválida: melhor falhar alto do que prometer um horário errado ao cliente."""


def _parse_time(value: str) -> time:
    try:
        hh, mm = value.split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError) as exc:
        raise StoreHoursError(f"horário inválido: {value!r} (use HH:MM)") from exc


def parse_hours(raw: str) -> dict[str, tuple[time, time]]:
    """`{"mon-fri": ["08:30","17:30"], "sat": [...], "holiday": [...]}` -> {"mon":(t,t),...,"holiday":(t,t)}. Dia ausente = sem atendimento."""
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise StoreHoursError("STORE_HOURS não é um JSON válido") from exc
    if not isinstance(data, dict):
        raise StoreHoursError("STORE_HOURS deve ser um objeto JSON")
    out: dict[str, tuple[time, time]] = {}
    for key, span in data.items():
        if not (isinstance(span, list) and len(span) == 2):
            raise StoreHoursError(f"{key}: use [abertura, fechamento]")
        opens, closes = _parse_time(span[0]), _parse_time(span[1])
        if opens >= closes:
            raise StoreHoursError(f"{key}: abertura deve ser anterior ao fechamento")
        if "-" in key and key != "holiday":
            a, b = key.split("-", 1)
            if a not in _DAYS or b not in _DAYS or _DAYS.index(a) > _DAYS.index(b):
                raise StoreHoursError(f"intervalo de dias inválido: {key!r}")
            keys = _DAYS[_DAYS.index(a): _DAYS.index(b) + 1]
        elif key in _DAYS or key == "holiday":
            keys = (key,)
        else:
            raise StoreHoursError(f"dia desconhecido: {key!r}")
        for k in keys:
            out[k] = (opens, closes)
    return out


def easter(year: int) -> date:
    """Domingo de Páscoa (algoritmo gregoriano anônimo)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _iso_dates(raw: str) -> set[date]:
    out = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if part:
            try:
                out.add(date.fromisoformat(part))
            except ValueError as exc:
                raise StoreHoursError(f"data inválida em feriados: {part!r} (use AAAA-MM-DD)") from exc
    return out


def holiday_name(d: date, s: Settings) -> str | None:
    if d in _iso_dates(s.store_excluded_holidays):
        return None
    if d in _iso_dates(s.store_extra_holidays):
        return "feriado cadastrado pela loja"
    if d == easter(d.year) - timedelta(days=2):
        return "Sexta-feira Santa"
    return _FIXED.get((d.month, d.day))


def hours_on(d: date, s: Settings) -> tuple[time, time] | None:
    """Horário de atendimento do dia, ou None (sem atendimento informado). Domingo nunca tem horário presumido."""
    hours = parse_hours(s.store_hours)
    weekday = d.weekday()
    if weekday == 6:
        return hours.get("sun")  # só se a loja informar explicitamente; feriado em domingo não cria horário
    if holiday_name(d, s):
        return hours.get("holiday")
    return hours.get(_DAYS[weekday])


def _local(moment: datetime, s: Settings) -> datetime:
    aware = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return aware.astimezone(ZoneInfo(s.store_timezone))


def is_open(moment: datetime, s: Settings, *, close_margin: timedelta = timedelta(0)) -> bool:
    local = _local(moment, s)
    span = hours_on(local.date(), s)
    if span is None:
        return False
    opens = local.replace(hour=span[0].hour, minute=span[0].minute, second=0, microsecond=0)
    closes = local.replace(hour=span[1].hour, minute=span[1].minute, second=0, microsecond=0) - close_margin
    return opens <= local < closes


def next_open(moment: datetime, s: Settings, *, close_margin: timedelta = timedelta(0)) -> datetime:
    """Primeiro instante >= moment em que a loja atende (UTC). Levanta se a configuração não tiver nenhum dia com atendimento."""
    local = _local(moment, s)
    for offset in range(0, 21):
        day = (local + timedelta(days=offset)).date()
        span = hours_on(day, s)
        if span is None:
            continue
        tz = ZoneInfo(s.store_timezone)
        opens = datetime(day.year, day.month, day.day, span[0].hour, span[0].minute, tzinfo=tz)
        closes = datetime(day.year, day.month, day.day, span[1].hour, span[1].minute, tzinfo=tz) - close_margin
        candidate = max(local, opens)
        if candidate < closes:
            return candidate.astimezone(timezone.utc)
    raise StoreHoursError("nenhum dia com atendimento nos próximos 21 dias na configuração de horário")


def describe(s: Settings) -> str:
    """Texto que o agente pode repetir ao cliente (somente o que está configurado)."""
    hours = parse_hours(s.store_hours)
    fmt = lambda span: f"{span[0].strftime('%H:%M')} às {span[1].strftime('%H:%M')}"  # noqa: E731
    groups: list[str] = []
    weekdays = [d for d in _DAYS[:5] if d in hours]
    if weekdays and len({hours[d] for d in weekdays}) == 1 and len(weekdays) == 5:
        groups.append(f"segunda a sexta: {fmt(hours['mon'])}")
    else:
        groups += [f"{_NAMES_PT[_DAYS.index(d)]}: {fmt(hours[d])}" for d in weekdays]
    if "sat" in hours:
        groups.append(f"sábado: {fmt(hours['sat'])}")
    if "sun" in hours:
        groups.append(f"domingo: {fmt(hours['sun'])}")
    if "holiday" in hours:
        groups.append(f"feriados: {fmt(hours['holiday'])}")
    text = "; ".join(groups) if groups else "horário não configurado"
    if "sun" not in hours:
        text += ". Domingo: sem atendimento informado — confirme com a equipe"
    return text + "."


def status_at(moment: datetime, s: Settings) -> dict:
    local = _local(moment, s)
    span = hours_on(local.date(), s)
    holiday = holiday_name(local.date(), s)
    return {
        "data": local.date().isoformat(), "dia_da_semana": _NAMES_PT[local.weekday()], "feriado": holiday,
        "horario_do_dia": None if span is None else f"{span[0].strftime('%H:%M')}–{span[1].strftime('%H:%M')}",
        "aberto_agora": is_open(moment, s), "horarios": describe(s),
        "observacao": "Feriados municipais/estaduais só valem se cadastrados pela loja; confirme com a equipe em caso de dúvida.",
    }
