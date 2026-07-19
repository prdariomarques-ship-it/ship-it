"""GoogleCalendarProvider — REST via httpx, no SDK. Mirrors the mocking
style used for Gmail/Gemini: patch `httpx.AsyncClient` at the module it's
imported into.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.calendar.base import (
    CalendarProviderError,
    EventSearchQuery,
    NewEvent,
    EventUpdate,
)
from providers.calendar.factory import (
    UnknownCalendarProviderError,
    get_calendar_provider,
)
from providers.calendar.google.provider import (
    GoogleCalendarProvider,
    _parse_event,
    _to_rfc3339,
)
from utils.config import get_settings


def _mock_response(json_body: dict, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.content = b"{}" if json_body else b""
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=json_body)
    return response


def _patch_client(request_result=None, post_result=None):
    """OAuth token calls (`post_result`) and API calls (`request_result`) both
    go through `google_http.google_request`, which always calls
    `client.request(method, url, ...)` — never `client.post` directly."""
    result = request_result if request_result is not None else post_result
    client = MagicMock()
    if result is not None:
        client.request = AsyncMock(
            side_effect=result if isinstance(result, list) else [result] * 20
        )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return patch(
        "providers.google_http.httpx.AsyncClient", return_value=client
    ), client


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "client-id")
    monkeypatch.setattr(get_settings(), "google_client_secret", "client-secret")
    monkeypatch.setattr(
        get_settings(),
        "google_calendar_redirect_uri",
        "https://app.example.com/api/gcalendar/oauth/callback",
    )
    return GoogleCalendarProvider()


def test_authorization_url_includes_offline_access_full_scope_and_state(provider):
    url = provider.authorization_url("the-state-token")
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "state=the-state-token" in url
    assert "auth%2Fcalendar" in url  # urlencoded scope


@pytest.mark.asyncio
async def test_exchange_code_returns_tokens(provider):
    body = {
        "access_token": "at1",
        "refresh_token": "rt1",
        "expires_in": 3600,
        "scope": "calendar",
    }
    patcher, client = _patch_client(post_result=_mock_response(body))
    with patcher:
        tokens = await provider.exchange_code("auth-code")
    assert tokens.access_token == "at1"
    assert tokens.refresh_token == "rt1"


@pytest.mark.asyncio
async def test_refresh_access_token_preserves_the_original_refresh_token(provider):
    body = {"access_token": "at2", "expires_in": 3600, "scope": "calendar"}
    patcher, _ = _patch_client(post_result=_mock_response(body))
    with patcher:
        tokens = await provider.refresh_access_token("original-refresh-token")
    assert tokens.access_token == "at2"
    assert tokens.refresh_token == "original-refresh-token"


@pytest.mark.asyncio
async def test_token_request_http_failure_raises_provider_error(provider, monkeypatch):
    import httpx as httpx_module

    monkeypatch.setattr(get_settings(), "google_request_backoff_seconds", 0)
    client = MagicMock()
    client.request = AsyncMock(side_effect=httpx_module.ConnectError("down"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "providers.google_http.httpx.AsyncClient", return_value=client
    ):
        with pytest.raises(CalendarProviderError):
            await provider.exchange_code("auth-code")


@pytest.mark.asyncio
async def test_list_calendars_parses_primary_flag(provider):
    body = {
        "items": [
            {
                "id": "primary",
                "summary": "Dario",
                "primary": True,
                "timeZone": "America/Sao_Paulo",
            },
            {"id": "cal2", "summary": "Trabalho", "timeZone": "America/Sao_Paulo"},
        ]
    }
    patcher, _ = _patch_client(request_result=[_mock_response(body)])
    with patcher:
        calendars = await provider.list_calendars("access-token")
    assert len(calendars) == 2
    assert calendars[0].primary is True
    assert calendars[1].primary is False


@pytest.mark.asyncio
async def test_search_events_parses_start_end_and_attendees(provider):
    body = {
        "items": [
            {
                "id": "e1",
                "summary": "Reunião",
                "status": "confirmed",
                "htmlLink": "https://calendar.google.com/e1",
                "start": {"dateTime": "2026-01-15T10:00:00-03:00"},
                "end": {"dateTime": "2026-01-15T11:00:00-03:00"},
                "attendees": [{"email": "a@example.com"}, {"email": "b@example.com"}],
            }
        ]
    }
    patcher, client = _patch_client(request_result=[_mock_response(body)])
    with patcher:
        events = await provider.search_events(
            "access-token", EventSearchQuery(calendar_id="primary", limit=10)
        )
    assert len(events) == 1
    assert events[0].summary == "Reunião"
    assert events[0].attendees == ["a@example.com", "b@example.com"]
    assert events[0].start == datetime(2026, 1, 15, 13, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_search_events_marks_all_day_events(provider):
    body = {
        "items": [
            {
                "id": "e2",
                "summary": "Feriado",
                "start": {"date": "2026-01-01"},
                "end": {"date": "2026-01-02"},
            }
        ]
    }
    patcher, _ = _patch_client(request_result=[_mock_response(body)])
    with patcher:
        events = await provider.search_events("access-token", EventSearchQuery())
    assert events[0].all_day is True


@pytest.mark.asyncio
async def test_search_events_api_failure_raises_provider_error(provider, monkeypatch):
    import httpx as httpx_module

    monkeypatch.setattr(get_settings(), "google_request_backoff_seconds", 0)
    client = MagicMock()
    client.request = AsyncMock(side_effect=httpx_module.ConnectError("down"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "providers.google_http.httpx.AsyncClient", return_value=client
    ):
        with pytest.raises(CalendarProviderError):
            await provider.search_events("access-token", EventSearchQuery())


@pytest.mark.asyncio
async def test_create_event_sends_expected_body_and_parses_response(provider):
    response_body = {
        "id": "new-event",
        "summary": "Café",
        "start": {"dateTime": "2026-02-01T09:00:00+00:00"},
        "end": {"dateTime": "2026-02-01T09:30:00+00:00"},
    }
    patcher, client = _patch_client(request_result=[_mock_response(response_body)])
    new_event = NewEvent(
        summary="Café",
        start=datetime(2026, 2, 1, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 2, 1, 9, 30, tzinfo=timezone.utc),
        attendees=["x@example.com"],
    )
    with patcher:
        event = await provider.create_event("access-token", "primary", new_event)
    assert event.id == "new-event"
    sent_body = client.request.call_args.kwargs["json"]
    assert sent_body["summary"] == "Café"
    assert sent_body["attendees"] == [{"email": "x@example.com"}]


@pytest.mark.asyncio
async def test_update_event_only_sends_provided_fields(provider):
    response_body = {"id": "e1", "summary": "Novo título"}
    patcher, client = _patch_client(request_result=[_mock_response(response_body)])
    update = EventUpdate(summary="Novo título")
    with patcher:
        event = await provider.update_event("access-token", "primary", "e1", update)
    assert event.summary == "Novo título"
    sent_body = client.request.call_args.kwargs["json"]
    assert sent_body == {"summary": "Novo título"}


@pytest.mark.asyncio
async def test_delete_event_calls_delete_and_returns_none(provider):
    patcher, client = _patch_client(
        request_result=[_mock_response({}, status_code=204)]
    )
    with patcher:
        result = await provider.delete_event("access-token", "primary", "e1")
    assert result is None
    assert client.request.call_args.args[0] == "DELETE"


@pytest.mark.asyncio
async def test_check_availability_reports_busy_and_conflicts(provider):
    freebusy_body = {
        "calendars": {
            "primary": {
                "busy": [
                    {"start": "2026-01-15T10:00:00Z", "end": "2026-01-15T11:00:00Z"}
                ]
            }
        }
    }
    events_body = {
        "items": [
            {
                "id": "e1",
                "summary": "Já marcado",
                "start": {"dateTime": "2026-01-15T10:00:00Z"},
                "end": {"dateTime": "2026-01-15T11:00:00Z"},
            }
        ]
    }
    patcher, client = _patch_client(
        request_result=[_mock_response(freebusy_body), _mock_response(events_body)]
    )
    with patcher:
        result = await provider.check_availability(
            "access-token",
            ["primary"],
            datetime(2026, 1, 15, 9, tzinfo=timezone.utc),
            datetime(2026, 1, 15, 12, tzinfo=timezone.utc),
        )
    assert result.is_free is False
    assert len(result.busy) == 1
    assert len(result.conflicting_events) == 1


@pytest.mark.asyncio
async def test_check_availability_free_when_no_busy_blocks(provider):
    freebusy_body = {"calendars": {"primary": {"busy": []}}}
    patcher, _ = _patch_client(request_result=[_mock_response(freebusy_body)])
    with patcher:
        result = await provider.check_availability(
            "access-token",
            ["primary"],
            datetime(2026, 1, 15, 9, tzinfo=timezone.utc),
            datetime(2026, 1, 15, 12, tzinfo=timezone.utc),
        )
    assert result.is_free is True
    assert result.busy == []
    assert result.conflicting_events == []


def test_to_rfc3339_attaches_utc_to_naive_datetime():
    assert _to_rfc3339(datetime(2026, 1, 1, 10, 0)) == "2026-01-01T10:00:00+00:00"


def test_parse_event_defaults_when_fields_missing():
    event = _parse_event({"id": "bare"}, "primary")
    assert event.summary == ""
    assert event.start is None
    assert event.attendees == []


def test_calendar_factory_resolves_google_by_default():
    get_calendar_provider.cache_clear()
    assert isinstance(get_calendar_provider(), GoogleCalendarProvider)
    get_calendar_provider.cache_clear()


def test_calendar_factory_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(get_settings(), "calendar_provider", "not-a-real-provider")
    get_calendar_provider.cache_clear()
    with pytest.raises(UnknownCalendarProviderError):
        get_calendar_provider()
    monkeypatch.setattr(get_settings(), "calendar_provider", "google")
    get_calendar_provider.cache_clear()
