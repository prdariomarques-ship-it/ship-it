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

from datetime import datetime, timezone

from agents.tools.base import Tool, ToolContext, ok
from providers.calendar.base import (
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
) -> str:
    access_token = await _get_access_token(context)
    provider = get_calendar_provider()
    update = EventUpdate(
        summary=summary,
        description=description,
        location=location,
        start=_parse_datetime(start),
        end=_parse_datetime(end),
        attendees=attendees,
    )
    try:
        event = await provider.update_event(access_token, calendar_id, event_id, update)
    except CalendarProviderError as exc:
        raise RuntimeError(f"Falha ao editar evento: {exc}") from exc
    return ok(event=_event_to_dict(event))


async def _delete_event(
    context: ToolContext, event_id: str, calendar_id: str = "primary"
) -> str:
    access_token = await _get_access_token(context)
    provider = get_calendar_provider()
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
    description="Cria um novo evento no Google Calendar.",
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
        },
        "required": ["summary", "start", "end"],
    },
)

update_google_calendar_event_tool = Tool(
    name="update_google_calendar_event",
    description="Edita um evento existente do Google Calendar (só os campos informados mudam).",
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
        },
        "required": ["event_id"],
    },
)

delete_google_calendar_event_tool = Tool(
    name="delete_google_calendar_event",
    description="Exclui um evento do Google Calendar.",
    handler=_delete_event,
    parameters={
        "type": "object",
        "properties": {
            "event_id": {"type": "string"},
            "calendar_id": {
                "type": "string",
                "description": "Id da agenda (padrão 'primary')",
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
