"""Gmail provider — REST via httpx, no new SDK dependency (same choice
already made for the Gemini LLM provider: `httpx` was already a dependency,
so a thin REST client beats pulling in `google-api-python-client` +
`google-auth` + `google-auth-httplib2` for what amounts to a handful of
endpoints.

Docs: https://developers.google.com/gmail/api/reference/rest
"""

import base64
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

import httpx

from providers.mail.base import (
    EmailMessage,
    EmailSearchQuery,
    EmailThread,
    MailProvider,
    MailProviderError,
    OAuthTokens,
)
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

# Read-only by design (Sprint 1 scope: read, search, summarize, detect —
# never send/reply/delete/modify labels). Requesting a narrower scope than
# the app could technically use is itself a security control, not just a
# convenience — Google won't grant what wasn't asked for.
GMAIL_SCOPES = "https://www.googleapis.com/auth/gmail.readonly"

_METADATA_HEADERS = ["Subject", "From", "To", "Date"]


class GmailProvider(MailProvider):
    name = "gmail"

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = settings.google_client_id
        self._client_secret = settings.google_client_secret
        self._redirect_uri = settings.google_redirect_uri
        self._oauth_base_url = settings.google_oauth_base_url
        self._token_url = settings.google_token_url
        self._api_base_url = settings.gmail_api_base_url.rstrip("/")

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": GMAIL_SCOPES,
            "access_type": "offline",
            # Force Google to (re)issue a refresh_token even if this account
            # already granted consent before — without this, a re-connect
            # after a revoked/lost token silently comes back without one.
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
        # Google's refresh grant doesn't repeat the refresh_token; callers
        # must keep using the one they already have.
        return result.model_copy(update={"refresh_token": refresh_token})

    async def _token_request(self, data: dict) -> OAuthTokens:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self._token_url, data=data)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Gmail OAuth token request failed: %s", exc)
            raise MailProviderError(f"Gmail OAuth token request failed: {exc}") from exc
        body = response.json()
        return OAuthTokens(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_in=body.get("expires_in", 3600),
            scope=body.get("scope", ""),
        )

    def _headers(self, access_token: str) -> dict:
        return {"Authorization": f"Bearer {access_token}"}

    async def _get(
        self, access_token: str, path: str, params: dict | None = None
    ) -> dict:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self._api_base_url}{path}",
                    headers=self._headers(access_token),
                    params=params,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Gmail API request failed (%s): %s", path, exc)
            raise MailProviderError(f"Gmail API request failed: {exc}") from exc
        return response.json()

    async def search(
        self, access_token: str, query: EmailSearchQuery
    ) -> list[EmailMessage]:
        result = await self._get(
            access_token,
            "/gmail/v1/users/me/messages",
            params={"q": _build_search_query(query), "maxResults": query.limit},
        )
        summaries = []
        for item in result.get("messages", []):
            detail = await self._get(
                access_token,
                f"/gmail/v1/users/me/messages/{quote(item['id'], safe='')}",
                params={"format": "metadata", "metadataHeaders": _METADATA_HEADERS},
            )
            summaries.append(_parse_message(detail, include_body=False))
        return summaries

    async def get_thread(self, access_token: str, thread_id: str) -> EmailThread:
        result = await self._get(
            access_token,
            f"/gmail/v1/users/me/threads/{quote(thread_id, safe='')}",
            params={"format": "full"},
        )
        messages = [
            _parse_message(raw, include_body=True) for raw in result.get("messages", [])
        ]
        subject = messages[0].subject if messages else ""
        return EmailThread(id=thread_id, subject=subject, messages=messages)


def _build_search_query(query: EmailSearchQuery) -> str:
    """Gmail's own search operators (from:, subject:, after:, before:,
    label:) — translating the normalized query into vendor syntax is exactly
    the kind of translation-only work that belongs in a Provider."""
    parts: list[str] = []
    if query.sender:
        parts.append(f"from:{query.sender}")
    if query.subject:
        parts.append(f'subject:"{query.subject}"')
    if query.since:
        parts.append(f"after:{query.since.strftime('%Y/%m/%d')}")
    if query.until:
        parts.append(f"before:{query.until.strftime('%Y/%m/%d')}")
    for label in query.labels:
        parts.append(f"label:{label}")
    if query.keywords:
        parts.append(query.keywords)
    return " ".join(parts)


def _header(headers: list[dict], name: str) -> str:
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def _decode_base64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def _extract_body(payload: dict) -> str:
    """Walk a MIME payload for the first text/plain part. Falls back to
    text/html (tags left as-is — good enough for an LLM to summarize;
    stripping HTML properly is not worth a new dependency for Sprint 1)."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")
    if mime_type == "text/plain" and body_data:
        return _decode_base64url(body_data)

    html_fallback = ""
    for part in payload.get("parts", []) or []:
        found = _extract_body(part)
        if found and part.get("mimeType") == "text/plain":
            return found
        if found and not html_fallback:
            html_fallback = found
    if html_fallback:
        return html_fallback
    if body_data:
        return _decode_base64url(body_data)
    return ""


def _parse_message(raw: dict, include_body: bool) -> EmailMessage:
    payload = raw.get("payload", {}) or {}
    headers = payload.get("headers", []) or []
    to_raw = _header(headers, "To")
    return EmailMessage(
        id=raw["id"],
        thread_id=raw.get("threadId", raw["id"]),
        sender=_header(headers, "From"),
        to=[addr.strip() for addr in to_raw.split(",") if addr.strip()],
        subject=_header(headers, "Subject"),
        snippet=raw.get("snippet", ""),
        body=_extract_body(payload) if include_body else "",
        date=_parse_date(_header(headers, "Date")),
        labels=raw.get("labelIds", []) or [],
    )
