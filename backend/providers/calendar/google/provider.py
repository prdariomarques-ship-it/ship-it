"""Google Calendar provider — REST via httpx, no new SDK dependency (same
choice already made for Gmail and Gemini: httpx is already a dependency).

Docs: https://developers.google.com/calendar/api/v3/reference
"""

from datetime import datetime, timezone

import httpx

from providers.calendar.base import (
    AvailabilityResult,
    CalendarEvent,
    CalendarInfo,
    CalendarProvider,
    CalendarProviderError,
    EventSearchQuery,
    EventUpdate,
    FreeBusyBlock,
    NewEvent,
    OAuthTokens,
)
from providers.google_http import google_request
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

# Read+write by design (Sprint 2 scope explicitly includes create/edit/delete,
# unlike Gmail's read-only Sprint 1) — narrower "calendar.events"-only scopes
# would still miss calendarList, so the single full-access scope is the
# correct minimum for the declared feature set, not overreach.
GOOGLE_CALENDAR_SCOPES = "https://www.googleapis.com/auth/calendar"


class GoogleCalendarProvider(CalendarProvider):
    name = "google"

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = settings.google_client_id
        self._client_secret = settings.google_client_secret
        self._redirect_uri = settings.google_calendar_redirect_uri
        self._oauth_base_url = settings.google_oauth_base_url
        self._token_url = settings.google_token_url
        self._api_base_url = settings.google_calendar_api_base_url.rstrip("/")

    def authorization_url(self, state: str) -> str:
        from urllib.parse import urlencode

        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_CALENDAR_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{self._oauth_base_url}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OAuthTokens:
        return await self._token_request(
            {
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
            }
        )

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        result = await self._token_request(
            {
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            }
        )
        return result.model_copy(update={"refresh_token": refresh_token})

    async def _token_request(self, data: dict) -> OAuthTokens:
        try:
            response = await google_request(
                "google_calendar", "POST", self._token_url, data=data
            )
        except httpx.HTTPError as exc:
            logger.error("Google Calendar OAuth token request failed: %s", exc)
            raise CalendarProviderError(
                f"Google Calendar OAuth token request failed: {exc}"
            ) from exc
        body = response.json()
        return OAuthTokens(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_in=body.get("expires_in", 3600),
            scope=body.get("scope", ""),
        )

    def _headers(self, access_token: str) -> dict:
        return {"Authorization": f"Bearer {access_token}"}

    async def _request(
        self, method: str, access_token: str, path: str, **kwargs
    ) -> dict:
        try:
            response = await google_request(
                "google_calendar",
                method,
                f"{self._api_base_url}{path}",
                headers=self._headers(access_token),
                **kwargs,
            )
        except httpx.HTTPError as exc:
            logger.error(
                "Google Calendar API request failed (%s %s): %s", method, path, exc
            )
            raise CalendarProviderError(
                f"Google Calendar API request failed: {exc}"
            ) from exc
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    async def list_calendars(self, access_token: str) -> list[CalendarInfo]:
        result = await self._request("GET", access_token, "/users/me/calendarList")
        return [
            CalendarInfo(
                id=item["id"],
                summary=item.get("summary", ""),
                primary=item.get("primary", False),
                time_zone=item.get("timeZone", ""),
            )
            for item in result.get("items", [])
        ]

    async def search_events(
        self, access_token: str, query: EventSearchQuery
    ) -> list[CalendarEvent]:
        params: dict = {
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": query.limit,
        }
        if query.query:
            params["q"] = query.query
        if query.since:
            params["timeMin"] = _to_rfc3339(query.since)
        if query.until:
            params["timeMax"] = _to_rfc3339(query.until)
        result = await self._request(
            "GET",
            access_token,
            f"/calendars/{_encode(query.calendar_id)}/events",
            params=params,
        )
        return [_parse_event(raw, query.calendar_id) for raw in result.get("items", [])]

    async def create_event(
        self, access_token: str, calendar_id: str, event: NewEvent
    ) -> CalendarEvent:
        body = {
            "summary": event.summary,
            "description": event.description,
            "location": event.location,
            "start": {"dateTime": _to_rfc3339(event.start)},
            "end": {"dateTime": _to_rfc3339(event.end)},
            "attendees": [{"email": address} for address in event.attendees],
        }
        raw = await self._request(
            "POST", access_token, f"/calendars/{_encode(calendar_id)}/events", json=body
        )
        return _parse_event(raw, calendar_id)

    async def update_event(
        self, access_token: str, calendar_id: str, event_id: str, update: EventUpdate
    ) -> CalendarEvent:
        body: dict = {}
        if update.summary is not None:
            body["summary"] = update.summary
        if update.description is not None:
            body["description"] = update.description
        if update.location is not None:
            body["location"] = update.location
        if update.start is not None:
            body["start"] = {"dateTime": _to_rfc3339(update.start)}
        if update.end is not None:
            body["end"] = {"dateTime": _to_rfc3339(update.end)}
        if update.attendees is not None:
            body["attendees"] = [{"email": address} for address in update.attendees]
        raw = await self._request(
            "PATCH",
            access_token,
            f"/calendars/{_encode(calendar_id)}/events/{_encode(event_id)}",
            json=body,
        )
        return _parse_event(raw, calendar_id)

    async def delete_event(
        self, access_token: str, calendar_id: str, event_id: str
    ) -> None:
        await self._request(
            "DELETE",
            access_token,
            f"/calendars/{_encode(calendar_id)}/events/{_encode(event_id)}",
        )

    async def check_availability(
        self,
        access_token: str,
        calendar_ids: list[str],
        since: datetime,
        until: datetime,
    ) -> AvailabilityResult:
        body = {
            "timeMin": _to_rfc3339(since),
            "timeMax": _to_rfc3339(until),
            "items": [{"id": calendar_id} for calendar_id in calendar_ids],
        }
        result = await self._request("POST", access_token, "/freeBusy", json=body)
        busy: list[FreeBusyBlock] = []
        for calendar_id in calendar_ids:
            calendar_data = result.get("calendars", {}).get(calendar_id, {})
            for block in calendar_data.get("busy", []):
                busy.append(
                    FreeBusyBlock(
                        start=_parse_rfc3339(block["start"]),
                        end=_parse_rfc3339(block["end"]),
                    )
                )

        conflicting_events: list[CalendarEvent] = []
        if busy:
            # freeBusy only reports blocks, not event details — one extra
            # search on the primary calendar gives the model something
            # actionable ("conflita com X") instead of just a time range.
            events = await self.search_events(
                access_token,
                EventSearchQuery(
                    calendar_id=calendar_ids[0], since=since, until=until, limit=10
                ),
            )
            conflicting_events = events

        return AvailabilityResult(
            is_free=not busy, busy=busy, conflicting_events=conflicting_events
        )


def _encode(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def _to_rfc3339(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _parse_rfc3339(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_event(raw: dict, calendar_id: str) -> CalendarEvent:
    start_field = raw.get("start", {}) or {}
    end_field = raw.get("end", {}) or {}
    all_day = "date" in start_field and "dateTime" not in start_field
    start = _parse_event_datetime(start_field)
    end = _parse_event_datetime(end_field)
    return CalendarEvent(
        id=raw["id"],
        calendar_id=calendar_id,
        summary=raw.get("summary", ""),
        description=raw.get("description", ""),
        location=raw.get("location", ""),
        start=start,
        end=end,
        all_day=all_day,
        attendees=[a["email"] for a in raw.get("attendees", []) if a.get("email")],
        status=raw.get("status", ""),
        html_link=raw.get("htmlLink", ""),
    )


def _parse_event_datetime(field: dict) -> datetime | None:
    if "dateTime" in field:
        return _parse_rfc3339(field["dateTime"])
    if "date" in field:
        try:
            return datetime.fromisoformat(field["date"]).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None
