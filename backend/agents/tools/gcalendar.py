"""Google Calendar tools — Sprint 2. Read+write: list calendars, search/list
events (covers "listar", "buscar", "próximos compromissos", "hoje/amanhã/
semana" via since/until — same consolidation Gmail's `search_emails` already
uses instead of one tool per date range), create, update, delete, and check
availability (covers both "verificar conflitos" and "consultar
disponibilidade" — both questions boil down to "what's busy in this
window").

Registered only on `agents/assistant_agent.py`. No other agent gets these —
the Calendar domain has exactly one technical gateway, same as Email. A
specialized agent that needs something from the calendar gets it through a
Cognitive Planner multi-step plan that routes one step to `assistant`,
never through direct tool access — see `docs/CALENDAR.md`.

These tools operate on the user's *Google* Calendar — unrelated to Dario
OS's own internal `create_task`/`create_event`/`list_events` tools
(`agents/tools/productivity.py`, backed by `models.calendar.CalendarEvent`),
which remain untouched and unaffected by this file.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from dateutil.rrule import rrulestr

from agents.tools.base import Tool, ToolContext, ok
from providers.calendar.base import (
    CalendarEvent,
    CalendarProvider,
    CalendarProviderError,
    EventSearchQuery,
    EventUpdate,
    NewEvent,
)
from providers.calendar.factory import get_calendar_provider
from repositories.gcalendar_account import GoogleCalendarAccountRepository
from services.token_crypto import TokenEncryptionNotConfigured, decrypt_token


class CalendarNotConnectedError(RuntimeError):
    """No Google Calendar authorized for this user — surfaced to the model
    as a normal tool error (via Tool.run's catch-all), same as any other
    tool failure. Never a crash, never a fallback to someone else's
    calendar."""


async def _get_access_token(context: ToolContext) -> str:
    """The only place a calendar account is chosen — always from
    `context.user.id` (set by the application, never by the model). Same
    principle as `agents/tools/mail.py::_get_access_token` (PROD-005 applied
    to the Calendar domain)."""
    if context.user is None:
        raise CalendarNotConnectedError("No authenticated user in context")

    provider = get_calendar_provider()
    account = await GoogleCalendarAccountRepository(context.db).get_by_user(
        context.user.id, provider.name
    )
    if account is None:
        raise CalendarNotConnectedError(
            "Nenhum Google Calendar conectado. Peça ao administrador para conectar em /api/gcalendar/connect."
        )
    try:
        refresh_token = decrypt_token(account.encrypted_refresh_token)
    except TokenEncryptionNotConfigured as exc:
        raise CalendarNotConnectedError(str(exc)) from exc

    try:
        tokens = await provider.refresh_access_token(refresh_token)
    except CalendarProviderError as exc:
        raise CalendarNotConnectedError(
            "A conexão com o Google Calendar expirou ou foi revogada. Peça ao administrador para "
            "reconectar em /api/gcalendar/connect."
        ) from exc
    return tokens.access_token


def _parse_datetime(value: str | None) -> datetime | None:
    """Accepts a full ISO datetime (with or without an offset) — unlike
    Gmail's date-only search filters, calendar events need actual times."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _require_datetime(value: str, field_name: str) -> datetime:
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ValueError(
            f"{field_name} deve ser uma data/hora ISO válida (ex: 2026-01-15T10:00:00)"
        )
    return parsed


_EVENT_SCOPES = ("this_event", "all_events", "this_and_following")

# Safety cap on `this_and_following`'s COUNT recalculation -- a personal
# calendar is nowhere near this; refusing explicitly beats silently
# enumerating a huge series.
_MAX_RRULE_COUNT_TO_SPLIT = 5000
_UNTIL_FORMAT = "%Y%m%dT%H%M%SZ"
_COUNT_RE = re.compile(r"COUNT=(\d+)")


class RecurrenceSplitNotSupportedError(RuntimeError):
    """`this_and_following` has a deliberately narrow, documented scope
    (see docs/CALENDAR.md) -- surfaced as a normal tool error (via
    Tool.run's catch-all), never a crash."""


async def _resolve_target_event_id(
    provider: CalendarProvider,
    access_token: str,
    calendar_id: str,
    event_id: str,
    scope: str,
) -> str:
    """`this_event` (default) is a no-op -- Google already scopes a PATCH/DELETE
    to just the given id, whether it's a plain event or one instance of a
    series (current, unchanged behavior). `all_events` resolves to the
    series' master id (`recurring_event_id`) so the edit/delete lands on the
    whole series; an event that isn't part of a series simply has no
    `recurring_event_id`, so it falls back to its own id -- a safe no-op,
    not an error, for a non-recurring event."""
    if scope not in _EVENT_SCOPES:
        raise ValueError(f"scope deve ser um de {_EVENT_SCOPES}, recebido: {scope!r}")
    if scope == "this_event":
        return event_id
    event = await provider.get_event(access_token, calendar_id, event_id)
    return event.recurring_event_id or event.id


@dataclass
class _SeriesSplit:
    instance: CalendarEvent
    master: CalendarEvent


async def _resolve_series_split(
    provider: CalendarProvider, access_token: str, calendar_id: str, event_id: str
) -> _SeriesSplit | None:
    """For `scope="this_and_following"` only. Returns `None` when there's no
    real split point -- either the event isn't part of any series (caller
    falls back to `this_event`), or `event_id` is already the series
    master itself, with no specific occurrence to split from (caller falls
    back to `all_events`) -- both already handled correctly by
    `_resolve_target_event_id`, reused as the fallback rather than
    reimplemented here."""
    event = await provider.get_event(access_token, calendar_id, event_id)
    if not event.recurring_event_id:
        return None
    master = await provider.get_event(access_token, calendar_id, event.recurring_event_id)
    return _SeriesSplit(instance=event, master=master)


def _single_rrule_line(recurrence: list[str] | None) -> str:
    """`this_and_following` only supports a series whose `recurrence` is
    exactly one plain RRULE line -- an EXRULE/RDATE/EXDATE alongside it
    could be silently dropped or misapplied by the split below, so that
    case is rejected explicitly instead of risked."""
    if not recurrence or len(recurrence) != 1 or not recurrence[0].startswith("RRULE:"):
        raise RecurrenceSplitNotSupportedError(
            "'this_and_following' só é suportado quando a série tem exatamente uma regra "
            "RRULE simples (sem EXRULE/RDATE/EXDATE)."
        )
    return recurrence[0]


def _format_until(value: datetime) -> str:
    # Google always reports timed (non-all-day) events with an explicit
    # UTC offset, so per RFC 5545 the RRULE's UNTIL must match: UTC with a
    # trailing "Z". dateutil's own serializer doesn't add it (confirmed by
    # inspection), so it's appended by hand rather than trusted to a
    # round-trip through the library.
    return value.astimezone(timezone.utc).strftime(_UNTIL_FORMAT)


def _set_rrule_until(rrule_line: str, until: datetime) -> str:
    """Rewrites the RRULE line to end at `until`. Targeted regex substitution
    on the raw line (not a re-serialization via dateutil) so every other
    part of the rule (FREQ/BYDAY/INTERVAL/WKST/...) is left untouched.
    COUNT and UNTIL can never coexist per RFC 5545, so an existing COUNT is
    replaced, not kept alongside the new UNTIL."""
    until_field = f"UNTIL={_format_until(until)}"
    if "COUNT=" in rrule_line:
        return _COUNT_RE.sub(until_field, rrule_line)
    if "UNTIL=" in rrule_line:
        return re.sub(r"UNTIL=[^;]+", until_field, rrule_line)
    return f"{rrule_line};{until_field}"


def _set_rrule_count(rrule_line: str, count: int) -> str:
    count_field = f"COUNT={count}"
    if "COUNT=" in rrule_line:
        return _COUNT_RE.sub(count_field, rrule_line)
    if "UNTIL=" in rrule_line:
        return re.sub(r"UNTIL=[^;]+", count_field, rrule_line)
    return f"{rrule_line};{count_field}"


def _continuation_rrule(rrule_line: str, series_start: datetime, split_start: datetime) -> str:
    """The RRULE for the new ("following") series, starting at the split
    point. A rule with no COUNT (UNTIL-bounded or unbounded) is reused
    unchanged -- still a valid, meaningful rule from any later start date.
    Only a COUNT-bounded rule needs recalculating, since the remaining
    number of occurrences depends on how many already happened before the
    split -- computed with a real RRULE engine (`dateutil`), not by hand."""
    match = _COUNT_RE.search(rrule_line)
    if match is None:
        return rrule_line
    original_count = int(match.group(1))
    if original_count > _MAX_RRULE_COUNT_TO_SPLIT:
        raise RecurrenceSplitNotSupportedError(
            "Série recorrente longa demais para dividir com segurança."
        )
    rule = rrulestr(rrule_line, dtstart=series_start)
    elapsed = rule.between(series_start - timedelta(seconds=1), split_start, inc=False)
    remaining = original_count - len(elapsed)
    if remaining <= 0:
        raise ValueError(
            "Não há ocorrências futuras a partir dessa data para dividir a série."
        )
    return _set_rrule_count(rrule_line, remaining)


async def _apply_this_and_following_update(
    provider: CalendarProvider,
    access_token: str,
    calendar_id: str,
    instance: CalendarEvent,
    master: CalendarEvent,
    update: EventUpdate,
) -> CalendarEvent:
    if instance.all_day or master.all_day:
        raise RecurrenceSplitNotSupportedError(
            "'this_and_following' não é suportado para eventos de dia inteiro nesta versão."
        )
    if instance.start is None or master.start is None:
        raise RecurrenceSplitNotSupportedError(
            "Evento sem data/hora de início definida."
        )
    new_end = update.end if update.end is not None else instance.end
    if new_end is None:
        raise RecurrenceSplitNotSupportedError(
            "Não foi possível determinar o horário de término da nova série."
        )
    original_rrule_line = _single_rrule_line(master.recurrence)

    # 1. Truncate the old series so it ends right before this occurrence --
    # everything before the split keeps its original values, untouched.
    truncated = _set_rrule_until(original_rrule_line, instance.start - timedelta(seconds=1))
    await provider.update_event(
        access_token, calendar_id, master.id, EventUpdate(recurrence=[truncated])
    )

    # 2. The new series' recurrence: an explicit `recurrence` from the
    # caller wins outright (they're deliberately changing the pattern from
    # here on); otherwise continue the old pattern.
    if update.recurrence is not None:
        new_recurrence = update.recurrence
    else:
        new_recurrence = [
            _continuation_rrule(original_rrule_line, master.start, instance.start)
        ]

    # 3. Create the new ("following") series at this occurrence, with the
    # updated fields -- falling back to the instance's own current values
    # for anything the caller didn't change (same "only informed fields
    # change" semantics as this_event/all_events).
    new_event = NewEvent(
        summary=update.summary if update.summary is not None else instance.summary,
        description=(
            update.description if update.description is not None else instance.description
        ),
        location=update.location if update.location is not None else instance.location,
        start=update.start if update.start is not None else instance.start,
        end=new_end,
        attendees=update.attendees if update.attendees is not None else instance.attendees,
        recurrence=new_recurrence,
    )
    return await provider.create_event(access_token, calendar_id, new_event)


async def _apply_this_and_following_delete(
    provider: CalendarProvider,
    access_token: str,
    calendar_id: str,
    instance: CalendarEvent,
    master: CalendarEvent,
) -> None:
    if instance.all_day or master.all_day:
        raise RecurrenceSplitNotSupportedError(
            "'this_and_following' não é suportado para eventos de dia inteiro nesta versão."
        )
    if instance.start is None:
        raise RecurrenceSplitNotSupportedError(
            "Evento sem data/hora de início definida."
        )
    original_rrule_line = _single_rrule_line(master.recurrence)
    truncated = _set_rrule_until(original_rrule_line, instance.start - timedelta(seconds=1))
    await provider.update_event(
        access_token, calendar_id, master.id, EventUpdate(recurrence=[truncated])
    )


async def _list_calendars(context: ToolContext) -> str:
    access_token = await _get_access_token(context)
    provider = get_calendar_provider()
    try:
        calendars = await provider.list_calendars(access_token)
    except CalendarProviderError as exc:
        raise RuntimeError(f"Falha ao listar agendas: {exc}") from exc
    return ok(
        calendars=[
            {
                "id": c.id,
                "summary": c.summary,
                "primary": c.primary,
                "time_zone": c.time_zone,
            }
            for c in calendars
        ]
    )


async def _search_events(
    context: ToolContext,
    calendar_id: str = "primary",
    query: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 20,
) -> str:
    access_token = await _get_access_token(context)
    provider = get_calendar_provider()
    search = EventSearchQuery(
        calendar_id=calendar_id,
        query=query,
        since=_parse_datetime(since),
        until=_parse_datetime(until),
        limit=min(limit, 50),
    )
    try:
        events = await provider.search_events(access_token, search)
    except CalendarProviderError as exc:
        raise RuntimeError(f"Falha ao buscar eventos: {exc}") from exc
    return ok(events=[_event_to_dict(e) for e in events])


async def _create_event(
    context: ToolContext,
    summary: str,
    start: str,
    end: str,
    calendar_id: str = "primary",
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
    recurrence: list[str] | None = None,
) -> str:
    access_token = await _get_access_token(context)
    provider = get_calendar_provider()
    new_event = NewEvent(
        summary=summary,
        description=description,
        location=location,
        start=_require_datetime(start, "start"),
        end=_require_datetime(end, "end"),
        attendees=attendees or [],
        recurrence=recurrence,
    )
    try:
        event = await provider.create_event(access_token, calendar_id, new_event)
    except CalendarProviderError as exc:
        raise RuntimeError(f"Falha ao criar evento: {exc}") from exc
    return ok(event=_event_to_dict(event))


async def _update_event(
    context: ToolContext,
    event_id: str,
    calendar_id: str = "primary",
    summary: str | None = None,
    description: str | None = None,
    location: str | None = None,
    start: str | None = None,
    end: str | None = None,
    attendees: list[str] | None = None,
    recurrence: list[str] | None = None,
    scope: str = "this_event",
) -> str:
    access_token = await _get_access_token(context)
    provider = get_calendar_provider()
    if scope not in _EVENT_SCOPES:
        raise ValueError(f"scope deve ser um de {_EVENT_SCOPES}, recebido: {scope!r}")
    update = EventUpdate(
        summary=summary,
        description=description,
        location=location,
        start=_parse_datetime(start),
        end=_parse_datetime(end),
        attendees=attendees,
        recurrence=recurrence,
    )
    try:
        if scope == "this_and_following":
            split = await _resolve_series_split(provider, access_token, calendar_id, event_id)
            if split is None:
                target_id = await _resolve_target_event_id(
                    provider, access_token, calendar_id, event_id, "all_events"
                )
                event = await provider.update_event(access_token, calendar_id, target_id, update)
            else:
                event = await _apply_this_and_following_update(
                    provider, access_token, calendar_id, split.instance, split.master, update
                )
        else:
            target_id = await _resolve_target_event_id(
                provider, access_token, calendar_id, event_id, scope
            )
            event = await provider.update_event(access_token, calendar_id, target_id, update)
    except CalendarProviderError as exc:
        raise RuntimeError(f"Falha ao editar evento: {exc}") from exc
    return ok(event=_event_to_dict(event))


async def _delete_event(
    context: ToolContext,
    event_id: str,
    calendar_id: str = "primary",
    scope: str = "this_event",
) -> str:
    access_token = await _get_access_token(context)
    provider = get_calendar_provider()
    if scope not in _EVENT_SCOPES:
        raise ValueError(f"scope deve ser um de {_EVENT_SCOPES}, recebido: {scope!r}")
    try:
        if scope == "this_and_following":
            split = await _resolve_series_split(provider, access_token, calendar_id, event_id)
            if split is None:
                event_id = await _resolve_target_event_id(
                    provider, access_token, calendar_id, event_id, "all_events"
                )
            else:
                await _apply_this_and_following_delete(
                    provider, access_token, calendar_id, split.instance, split.master
                )
                return ok(deleted=True, event_id=split.master.id, truncated=True)
        else:
            event_id = await _resolve_target_event_id(
                provider, access_token, calendar_id, event_id, scope
            )
    except CalendarProviderError as exc:
        raise RuntimeError(f"Falha ao excluir evento: {exc}") from exc
    try:
        await provider.delete_event(access_token, calendar_id, event_id)
    except CalendarProviderError as exc:
        raise RuntimeError(f"Falha ao excluir evento: {exc}") from exc
    return ok(deleted=True, event_id=event_id)


async def _check_availability(
    context: ToolContext,
    start: str,
    end: str,
    calendar_ids: list[str] | None = None,
) -> str:
    access_token = await _get_access_token(context)
    provider = get_calendar_provider()
    since = _require_datetime(start, "start")
    until = _require_datetime(end, "end")
    ids = calendar_ids or ["primary"]
    try:
        result = await provider.check_availability(access_token, ids, since, until)
    except CalendarProviderError as exc:
        raise RuntimeError(f"Falha ao consultar disponibilidade: {exc}") from exc
    return ok(
        is_free=result.is_free,
        busy=[{"start": b.start, "end": b.end} for b in result.busy],
        conflicting_events=[_event_to_dict(e) for e in result.conflicting_events],
    )


def _event_to_dict(event) -> dict:
    return {
        "id": event.id,
        "calendar_id": event.calendar_id,
        "summary": event.summary,
        "description": event.description,
        "location": event.location,
        "start": event.start,
        "end": event.end,
        "all_day": event.all_day,
        "attendees": event.attendees,
        "status": event.status,
        "html_link": event.html_link,
        "recurrence": event.recurrence,
        "recurring_event_id": event.recurring_event_id,
    }


list_google_calendars_tool = Tool(
    name="list_google_calendars",
    description="Lista as agendas (calendários) do Google Calendar conectado.",
    handler=_list_calendars,
    parameters={"type": "object", "properties": {}, "required": []},
)

search_google_calendar_events_tool = Tool(
    name="search_google_calendar_events",
    description=(
        "Busca ou lista eventos do Google Calendar por período e/ou palavra-chave. Use `since`/`until` "
        "para 'hoje', 'amanhã', 'esta semana' ou 'próximos compromissos' (calcule as datas ISO "
        "correspondentes antes de chamar)."
    ),
    handler=_search_events,
    parameters={
        "type": "object",
        "properties": {
            "calendar_id": {
                "type": "string",
                "description": "Id da agenda (padrão 'primary')",
            },
            "query": {"type": "string", "description": "Palavras-chave livres"},
            "since": {
                "type": "string",
                "description": "Data/hora ISO, início do período",
            },
            "until": {"type": "string", "description": "Data/hora ISO, fim do período"},
            "limit": {
                "type": "integer",
                "description": "Máximo de resultados (padrão 20)",
            },
        },
        "required": [],
    },
)

create_google_calendar_event_tool = Tool(
    name="create_google_calendar_event",
    description="Cria um novo evento no Google Calendar. Para um evento recorrente, informe `recurrence`.",
    handler=_create_event,
    parameters={
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Título do evento"},
            "start": {"type": "string", "description": "Data/hora ISO de início"},
            "end": {"type": "string", "description": "Data/hora ISO de término"},
            "calendar_id": {
                "type": "string",
                "description": "Id da agenda (padrão 'primary')",
            },
            "description": {"type": "string"},
            "location": {"type": "string"},
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "E-mails dos convidados",
            },
            "recurrence": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Regra de recorrência no formato RRULE do Google Calendar, ex: "
                    "['RRULE:FREQ=WEEKLY;BYDAY=MO;COUNT=10'] para toda segunda, 10 vezes, ou "
                    "['RRULE:FREQ=WEEKLY;UNTIL=20261231T000000Z'] para toda semana até uma data. "
                    "Omita para um evento único (não recorrente)."
                ),
            },
        },
        "required": ["summary", "start", "end"],
    },
)

update_google_calendar_event_tool = Tool(
    name="update_google_calendar_event",
    description=(
        "Edita um evento existente do Google Calendar (só os campos informados mudam). Se o evento "
        "fizer parte de uma série recorrente, use `scope` para escolher entre editar só esta "
        "ocorrência (padrão), a série inteira, ou esta ocorrência e as seguintes."
    ),
    handler=_update_event,
    parameters={
        "type": "object",
        "properties": {
            "event_id": {"type": "string"},
            "calendar_id": {
                "type": "string",
                "description": "Id da agenda (padrão 'primary')",
            },
            "summary": {"type": "string"},
            "description": {"type": "string"},
            "location": {"type": "string"},
            "start": {"type": "string", "description": "Nova data/hora ISO de início"},
            "end": {"type": "string", "description": "Nova data/hora ISO de término"},
            "attendees": {"type": "array", "items": {"type": "string"}},
            "recurrence": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Nova regra RRULE. Com scope='all_events', substitui a regra da série inteira. "
                    "Com scope='this_and_following', define a regra da nova série a partir desta "
                    "ocorrência (se omitido, a regra antiga continua, ajustada automaticamente)."
                ),
            },
            "scope": {
                "type": "string",
                "enum": ["this_event", "all_events", "this_and_following"],
                "description": (
                    "'this_event' (padrão): edita só esta ocorrência. 'all_events': edita a série "
                    "recorrente inteira -- use quando o usuário disser 'todos os eventos', 'a série "
                    "inteira', 'sempre'. 'this_and_following': edita esta ocorrência e todas as "
                    "seguintes, mantendo as anteriores intactas -- use quando o usuário disser 'a "
                    "partir de agora', 'esta e as próximas', 'daqui pra frente'. Suportado só para "
                    "eventos com horário definido (não dia inteiro) e cuja série tenha uma única "
                    "regra RRULE simples."
                ),
            },
        },
        "required": ["event_id"],
    },
)

delete_google_calendar_event_tool = Tool(
    name="delete_google_calendar_event",
    description=(
        "Exclui um evento do Google Calendar. Se o evento fizer parte de uma série recorrente, use "
        "`scope` para escolher entre excluir só esta ocorrência (padrão), a série inteira, ou esta "
        "ocorrência e as seguintes."
    ),
    handler=_delete_event,
    parameters={
        "type": "object",
        "properties": {
            "event_id": {"type": "string"},
            "calendar_id": {
                "type": "string",
                "description": "Id da agenda (padrão 'primary')",
            },
            "scope": {
                "type": "string",
                "enum": ["this_event", "all_events", "this_and_following"],
                "description": (
                    "'this_event' (padrão): exclui só esta ocorrência. 'all_events': exclui a série "
                    "recorrente inteira -- use quando o usuário disser 'todos os eventos', 'a série "
                    "inteira', 'sempre'. 'this_and_following': exclui esta ocorrência e todas as "
                    "seguintes, mantendo as anteriores -- use quando o usuário disser 'a partir de "
                    "agora', 'esta e as próximas', 'daqui pra frente'. Suportado só para eventos com "
                    "horário definido (não dia inteiro) e cuja série tenha uma única regra RRULE "
                    "simples."
                ),
            },
        },
        "required": ["event_id"],
    },
)

check_google_calendar_availability_tool = Tool(
    name="check_google_calendar_availability",
    description=(
        "Verifica disponibilidade/conflitos em um período: use antes de criar um evento para checar "
        "conflitos, ou para responder se um horário está livre."
    ),
    handler=_check_availability,
    parameters={
        "type": "object",
        "properties": {
            "start": {
                "type": "string",
                "description": "Data/hora ISO de início do período",
            },
            "end": {
                "type": "string",
                "description": "Data/hora ISO de término do período",
            },
            "calendar_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ids das agendas a checar (padrão ['primary'])",
            },
        },
        "required": ["start", "end"],
    },
)
