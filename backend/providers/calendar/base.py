"""Provider-agnostic Google Calendar contract (Strategy pattern) — Sprint 2:
Google only, but shaped the same as `providers/mail/base.py` so a second
provider (Outlook/Microsoft Graph, CalDAV) is a new class + a factory entry,
never a change to callers.

A Provider's job is translation and transport only: turn its vendor's API
shape into the neutral types below. No business logic, no database access,
no LLM calls — those belong to `agents/tools/gcalendar.py` and `gcalendar/`.

`CalendarEvent` here is a remote *Google* Calendar event — deliberately not
named the same as `models.calendar.CalendarEvent`, which is Dario OS's own
internal event storage (the `create_event`/`list_events` tools) and has
nothing to do with this integration. See `docs/CALENDAR.md`.
"""
from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class CalendarProviderError(RuntimeError):
    pass


class CalendarInfo(BaseModel):
    id: str
    summary: str = ""
    primary: bool = False
    time_zone: str = ""


class CalendarEvent(BaseModel):
    """A single Google Calendar event, normalized across providers."""

    id: str
    calendar_id: str
    summary: str = ""
    description: str = ""
    location: str = ""
    start: datetime | None = None
    end: datetime | None = None
    all_day: bool = False
    attendees: list[str] = []
    status: str = ""
    html_link: str = ""


class EventSearchQuery(BaseModel):
    calendar_id: str = "primary"
    query: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 20


class NewEvent(BaseModel):
    summary: str
    description: str = ""
    location: str = ""
    start: datetime
    end: datetime
    attendees: list[str] = []


class EventUpdate(BaseModel):
    summary: str | None = None
    description: str | None = None
    location: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    attendees: list[str] | None = None


class FreeBusyBlock(BaseModel):
    start: datetime
    end: datetime


class AvailabilityResult(BaseModel):
    """Answers both "verificar conflitos" (call with a proposed event's
    window) and "consultar disponibilidade" (call to check a free slot) —
    the underlying question is the same: what's busy in this window."""

    is_free: bool
    busy: list[FreeBusyBlock] = []
    conflicting_events: list[CalendarEvent] = []


class OAuthTokens(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int = 3600
    scope: str = ""


class CalendarProvider(ABC):
    """Strategy interface implemented by every calendar integration."""

    name: str

    @abstractmethod
    def authorization_url(self, state: str) -> str:
        """Build the URL the browser is redirected to for consent."""

    @abstractmethod
    async def exchange_code(self, code: str) -> OAuthTokens:
        """Exchange an OAuth authorization code for tokens (first connect)."""

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        """Exchange a stored refresh token for a fresh access token."""

    @abstractmethod
    async def list_calendars(self, access_token: str) -> list[CalendarInfo]:
        """List calendars the authorized account has access to."""

    @abstractmethod
    async def search_events(self, access_token: str, query: EventSearchQuery) -> list[CalendarEvent]:
        """Search/list events in one calendar (covers "listar", "buscar",
        "próximos compromissos", "hoje/amanhã/semana" via since/until)."""

    @abstractmethod
    async def create_event(self, access_token: str, calendar_id: str, event: NewEvent) -> CalendarEvent:
        """Create a new event."""

    @abstractmethod
    async def update_event(
        self, access_token: str, calendar_id: str, event_id: str, update: EventUpdate
    ) -> CalendarEvent:
        """Patch an existing event (only the provided fields change)."""

    @abstractmethod
    async def delete_event(self, access_token: str, calendar_id: str, event_id: str) -> None:
        """Delete an event."""

    @abstractmethod
    async def check_availability(
        self, access_token: str, calendar_ids: list[str], since: datetime, until: datetime
    ) -> AvailabilityResult:
        """Free/busy for a time window, across one or more calendars."""
