"""Google Calendar agent tools (Sprint 2) — unit, authorization and
cross-user isolation tests. Mirrors `tests/test_mail_tools.py`.
"""

import json
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

from agents.tools.base import ToolContext
from agents.tools.gcalendar import (
    CalendarNotConnectedError,
    _get_access_token,
    check_google_calendar_availability_tool,
    create_google_calendar_event_tool,
    delete_google_calendar_event_tool,
    list_google_calendars_tool,
    search_google_calendar_events_tool,
    update_google_calendar_event_tool,
)
from models.gcalendar_account import GoogleCalendarAccount
from models.user import User
from providers.calendar.base import (
    AvailabilityResult,
    CalendarEvent,
    CalendarInfo,
    CalendarProvider,
    CalendarProviderError,
)
from repositories.gcalendar_account import GoogleCalendarAccountRepository
from services.token_crypto import encrypt_token
from utils.config import get_settings


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "email_token_encryption_key", Fernet.generate_key().decode()
    )


@pytest.fixture
async def session_factory(db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def user_a(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="cal-a@example.com", full_name="A", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def user_b(session_factory) -> User:
    async with session_factory() as session:
        user = User(email="cal-b@example.com", full_name="B", hashed_password="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _connect(
    session_factory, user: User, refresh_token: str, label: str
) -> GoogleCalendarAccount:
    async with session_factory() as session:
        return await GoogleCalendarAccountRepository(session).create(
            user_id=user.id,
            provider="google",
            account_label=label,
            encrypted_refresh_token=encrypt_token(refresh_token),
            scopes=["calendar"],
            connected_at=datetime.now(timezone.utc),
        )


class FakeCalendarProvider(CalendarProvider):
    """Mailbox-analog for calendars — events keyed by access token."""

    name = "google"

    def __init__(
        self, calendars_by_token: dict[str, list[CalendarEvent]] | None = None
    ) -> None:
        self.events_by_token = calendars_by_token or {}
        self.calls: list[str] = []
        self.created_events: list = []
        self.update_calls: list[tuple[str, object]] = []
        self.delete_calls: list[str] = []

    def authorization_url(self, state: str) -> str:
        raise NotImplementedError

    async def exchange_code(self, code: str):
        raise NotImplementedError

    async def refresh_access_token(self, refresh_token: str):
        from providers.calendar.base import OAuthTokens

        return OAuthTokens(access_token=f"access-for-{refresh_token}")

    async def list_calendars(self, access_token: str) -> list[CalendarInfo]:
        self.calls.append(access_token)
        return [
            CalendarInfo(
                id="primary", summary=f"Agenda de {access_token}", primary=True
            )
        ]

    async def search_events(self, access_token: str, query) -> list[CalendarEvent]:
        self.calls.append(access_token)
        return self.events_by_token.get(access_token, [])

    async def get_event(
        self, access_token: str, calendar_id: str, event_id: str
    ) -> CalendarEvent:
        self.calls.append(access_token)
        for event in self.events_by_token.get(access_token, []):
            if event.id == event_id:
                return event
        return _event(access_token, event_id)

    async def create_event(
        self, access_token: str, calendar_id: str, event
    ) -> CalendarEvent:
        self.calls.append(access_token)
        self.created_events.append(event)
        created = _event(access_token, "new-event")
        return created.model_copy(update={"recurrence": event.recurrence})

    async def update_event(
        self, access_token: str, calendar_id: str, event_id: str, update
    ) -> CalendarEvent:
        self.calls.append(access_token)
        self.update_calls.append((event_id, update))
        return _event(access_token, event_id)

    async def delete_event(
        self, access_token: str, calendar_id: str, event_id: str
    ) -> None:
        self.calls.append(access_token)
        self.delete_calls.append(event_id)

    async def check_availability(
        self, access_token: str, calendar_ids, since, until
    ) -> AvailabilityResult:
        self.calls.append(access_token)
        events = self.events_by_token.get(access_token, [])
        return AvailabilityResult(
            is_free=not events, busy=[], conflicting_events=events
        )


def _event(
    tag: str, event_id: str = "e1", recurring_event_id: str | None = None
) -> CalendarEvent:
    return CalendarEvent(
        id=event_id,
        calendar_id="primary",
        summary=f"Evento confidencial de {tag}",
        recurring_event_id=recurring_event_id,
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
    )


# --- _get_access_token -----------------------------------------------------------
@pytest.mark.asyncio
async def test_get_access_token_resolves_strictly_from_context_user_id(
    session_factory, user_a, user_b, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    await _connect(session_factory, user_b, "rt-b", "b")
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: FakeCalendarProvider()
    )

    async with session_factory() as session:
        token_a = await _get_access_token(ToolContext(db=session, user=user_a))
    async with session_factory() as session:
        token_b = await _get_access_token(ToolContext(db=session, user=user_b))

    assert token_a == "access-for-rt-a"
    assert token_b == "access-for-rt-b"


@pytest.mark.asyncio
async def test_get_access_token_raises_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        with pytest.raises(CalendarNotConnectedError):
            await _get_access_token(ToolContext(db=session, user=user_a))


@pytest.mark.asyncio
async def test_get_access_token_treats_a_revoked_refresh_token_as_not_connected(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")

    class _RevokedProvider(FakeCalendarProvider):
        async def refresh_access_token(self, refresh_token):
            raise CalendarProviderError("invalid_grant")

    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: _RevokedProvider()
    )
    async with session_factory() as session:
        with pytest.raises(CalendarNotConnectedError, match="reconectar"):
            await _get_access_token(ToolContext(db=session, user=user_a))


# --- authorization: tools reject cleanly when nothing is connected -------------
@pytest.mark.asyncio
async def test_list_calendars_tool_rejects_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        result = await list_google_calendars_tool.run(
            ToolContext(db=session, user=user_a), {}
        )
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_search_events_tool_rejects_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        result = await search_google_calendar_events_tool.run(
            ToolContext(db=session, user=user_a), {}
        )
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_create_event_tool_rejects_when_not_connected(session_factory, user_a):
    async with session_factory() as session:
        result = await create_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a),
            {
                "summary": "x",
                "start": "2026-01-01T10:00:00",
                "end": "2026-01-01T11:00:00",
            },
        )
    assert "error" in json.loads(result)


# --- isolation: two connected users, zero cross-user leakage -------------------
@pytest.mark.asyncio
async def test_search_events_tool_never_returns_another_users_calendar(
    session_factory, user_a, user_b, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    await _connect(session_factory, user_b, "rt-b", "b")
    provider = FakeCalendarProvider(
        {"access-for-rt-a": [_event("a")], "access-for-rt-b": [_event("b")]}
    )
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )

    async with session_factory() as session:
        result_a = await search_google_calendar_events_tool.run(
            ToolContext(db=session, user=user_a), {}
        )
    async with session_factory() as session:
        result_b = await search_google_calendar_events_tool.run(
            ToolContext(db=session, user=user_b), {}
        )

    events_a = json.loads(result_a)["events"]
    events_b = json.loads(result_b)["events"]
    assert events_a[0]["summary"] == "Evento confidencial de a"
    assert events_b[0]["summary"] == "Evento confidencial de b"
    assert provider.calls == ["access-for-rt-a", "access-for-rt-b"]


@pytest.mark.asyncio
async def test_create_event_tool_uses_the_requesting_users_own_calendar(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeCalendarProvider()
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )

    async with session_factory() as session:
        result = await create_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a),
            {
                "summary": "Reunião",
                "start": "2026-01-01T10:00:00",
                "end": "2026-01-01T11:00:00",
            },
        )
    payload = json.loads(result)
    assert payload["ok"] is True
    assert provider.calls == ["access-for-rt-a"]


@pytest.mark.asyncio
async def test_search_events_tool_maps_provider_error_to_a_tool_error(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")

    class _FailingProvider(FakeCalendarProvider):
        async def search_events(self, access_token, query):
            raise CalendarProviderError("google is down")

    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: _FailingProvider()
    )
    async with session_factory() as session:
        result = await search_google_calendar_events_tool.run(
            ToolContext(db=session, user=user_a), {}
        )
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_create_event_tool_rejects_invalid_dates(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: FakeCalendarProvider()
    )
    async with session_factory() as session:
        result = await create_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a),
            {"summary": "x", "start": "not-a-date", "end": "also-not-a-date"},
        )
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_delete_event_tool_success(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeCalendarProvider()
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )
    async with session_factory() as session:
        result = await delete_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a), {"event_id": "e1"}
        )
    assert json.loads(result)["deleted"] is True


@pytest.mark.asyncio
async def test_update_event_tool_success(session_factory, user_a, monkeypatch):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeCalendarProvider()
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )
    async with session_factory() as session:
        result = await update_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a),
            {"event_id": "e1", "summary": "Novo título"},
        )
    assert json.loads(result)["ok"] is True


@pytest.mark.asyncio
async def test_check_availability_tool_never_reveals_another_users_conflicts(
    session_factory, user_a, user_b, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    await _connect(session_factory, user_b, "rt-b", "b")
    provider = FakeCalendarProvider(
        {"access-for-rt-a": [_event("a")], "access-for-rt-b": []}
    )
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )

    async with session_factory() as session:
        result_b = await check_google_calendar_availability_tool.run(
            ToolContext(db=session, user=user_b),
            {"start": "2026-01-01T00:00:00", "end": "2026-01-02T00:00:00"},
        )
    payload = json.loads(result_b)
    assert payload["is_free"] is True
    assert payload["conflicting_events"] == []


# --- recurring series: create, and scope resolution on update/delete -----------
@pytest.mark.asyncio
async def test_create_event_tool_passes_recurrence_through_to_the_provider(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeCalendarProvider()
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )
    async with session_factory() as session:
        result = await create_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a),
            {
                "summary": "Reunião semanal",
                "start": "2026-01-01T10:00:00",
                "end": "2026-01-01T11:00:00",
                "recurrence": ["RRULE:FREQ=WEEKLY;COUNT=10"],
            },
        )
    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["event"]["recurrence"] == ["RRULE:FREQ=WEEKLY;COUNT=10"]
    assert provider.created_events[0].recurrence == ["RRULE:FREQ=WEEKLY;COUNT=10"]


@pytest.mark.asyncio
async def test_create_event_tool_omits_recurrence_for_a_plain_event(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeCalendarProvider()
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )
    async with session_factory() as session:
        result = await create_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a),
            {
                "summary": "Consulta única",
                "start": "2026-01-01T10:00:00",
                "end": "2026-01-01T11:00:00",
            },
        )
    payload = json.loads(result)
    assert payload["event"]["recurrence"] is None
    assert provider.created_events[0].recurrence is None


@pytest.mark.asyncio
async def test_update_event_tool_default_scope_targets_only_the_given_instance(
    session_factory, user_a, monkeypatch
):
    """`this_event` (the default) is a no-op resolution -- no extra provider
    call, and the update lands on exactly the id the caller passed in,
    whether or not it happens to be part of a series."""
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeCalendarProvider(
        {"access-for-rt-a": [_event("a", "instance-1", recurring_event_id="master-1")]}
    )
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )
    async with session_factory() as session:
        result = await update_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a),
            {"event_id": "instance-1", "summary": "Só esta ocorrência"},
        )
    assert json.loads(result)["ok"] is True
    assert provider.update_calls == [("instance-1", provider.update_calls[0][1])]
    assert provider.calls.count("access-for-rt-a") == 1  # only the update call, no get_event


@pytest.mark.asyncio
async def test_update_event_tool_all_events_scope_resolves_to_the_series_master(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeCalendarProvider(
        {"access-for-rt-a": [_event("a", "instance-1", recurring_event_id="master-1")]}
    )
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )
    async with session_factory() as session:
        result = await update_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a),
            {
                "event_id": "instance-1",
                "summary": "Toda a série",
                "scope": "all_events",
            },
        )
    assert json.loads(result)["ok"] is True
    assert provider.update_calls[0][0] == "master-1"


@pytest.mark.asyncio
async def test_update_event_tool_all_events_scope_is_a_safe_no_op_for_a_non_recurring_event(
    session_factory, user_a, monkeypatch
):
    """An event with no `recurring_event_id` (not part of a series) falls
    back to its own id -- scope="all_events" never errors just because the
    event turned out not to be recurring."""
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeCalendarProvider({"access-for-rt-a": [_event("a", "e1")]})
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )
    async with session_factory() as session:
        result = await update_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a),
            {"event_id": "e1", "summary": "x", "scope": "all_events"},
        )
    assert json.loads(result)["ok"] is True
    assert provider.update_calls[0][0] == "e1"


@pytest.mark.asyncio
async def test_update_event_tool_rejects_an_invalid_scope(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeCalendarProvider()
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )
    async with session_factory() as session:
        result = await update_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a),
            {"event_id": "e1", "summary": "x", "scope": "not-a-real-scope"},
        )
    assert "error" in json.loads(result)
    assert provider.update_calls == []


@pytest.mark.asyncio
async def test_delete_event_tool_all_events_scope_resolves_to_the_series_master(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeCalendarProvider(
        {"access-for-rt-a": [_event("a", "instance-1", recurring_event_id="master-1")]}
    )
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )
    async with session_factory() as session:
        result = await delete_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a),
            {"event_id": "instance-1", "scope": "all_events"},
        )
    payload = json.loads(result)
    assert payload["deleted"] is True
    assert payload["event_id"] == "master-1"
    assert provider.delete_calls == ["master-1"]


@pytest.mark.asyncio
async def test_delete_event_tool_default_scope_deletes_only_the_given_instance(
    session_factory, user_a, monkeypatch
):
    await _connect(session_factory, user_a, "rt-a", "a")
    provider = FakeCalendarProvider(
        {"access-for-rt-a": [_event("a", "instance-1", recurring_event_id="master-1")]}
    )
    monkeypatch.setattr(
        "agents.tools.gcalendar.get_calendar_provider", lambda: provider
    )
    async with session_factory() as session:
        result = await delete_google_calendar_event_tool.run(
            ToolContext(db=session, user=user_a), {"event_id": "instance-1"}
        )
    payload = json.loads(result)
    assert payload["deleted"] is True
    assert payload["event_id"] == "instance-1"
    assert provider.delete_calls == ["instance-1"]
