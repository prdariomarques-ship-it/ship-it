"""Google Contacts provider — People API via httpx, no new SDK dependency
(same choice already made for Gmail and Google Calendar).

Docs: https://developers.google.com/people/api/rest
"""
import re
from urllib.parse import urlencode

import httpx

from providers.contacts.base import (
    Contact,
    ContactsProvider,
    ContactsProviderError,
    ContactSearchQuery,
    ContactUpdate,
    NewContact,
    OAuthTokens,
)
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

# Read+write (Sprint 2 scope includes create/edit/delete, unlike Gmail's
# read-only Sprint 1).
GOOGLE_CONTACTS_SCOPES = "https://www.googleapis.com/auth/contacts"

_PERSON_FIELDS = "names,emailAddresses,phoneNumbers"
# People API list pagination is not implemented — a personal instance's
# address book fits comfortably in one page at this size; see docs/CONTACTS.md.
_MAX_LIST_PAGE_SIZE = 1000

# `resource_name` legitimately contains a literal "/" (People API resource
# names are "people/<id>", not an opaque single-segment id like Gmail's
# thread_id or Drive's file_id) — it can't be `urllib.parse.quote`d the way
# those are without breaking the normal case. Validated against an allowlist
# instead: a model-supplied value with a stray "/" or "?" would otherwise
# change which People API path gets requested (e.g. "people/c1/../otherContacts/x").
_RESOURCE_NAME_RE = re.compile(r"^people/[A-Za-z0-9_-]+$")


class InvalidResourceNameError(ContactsProviderError):
    pass


def _validate_resource_name(resource_name: str) -> None:
    if not _RESOURCE_NAME_RE.match(resource_name):
        raise InvalidResourceNameError(f"Invalid contact resource_name: {resource_name!r}")


class GoogleContactsProvider(ContactsProvider):
    name = "google"

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = settings.google_client_id
        self._client_secret = settings.google_client_secret
        self._redirect_uri = settings.google_contacts_redirect_uri
        self._oauth_base_url = settings.google_oauth_base_url
        self._token_url = settings.google_token_url
        self._api_base_url = settings.google_people_api_base_url.rstrip("/")

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_CONTACTS_SCOPES,
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
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self._token_url, data=data)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Google Contacts OAuth token request failed: %s", exc)
            raise ContactsProviderError(f"Google Contacts OAuth token request failed: {exc}") from exc
        body = response.json()
        return OAuthTokens(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_in=body.get("expires_in", 3600),
            scope=body.get("scope", ""),
        )

    def _headers(self, access_token: str) -> dict:
        return {"Authorization": f"Bearer {access_token}"}

    async def _request(self, method: str, access_token: str, path: str, **kwargs) -> dict:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.request(
                    method, f"{self._api_base_url}{path}", headers=self._headers(access_token), **kwargs
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Google People API request failed (%s %s): %s", method, path, exc)
            raise ContactsProviderError(f"Google People API request failed: {exc}") from exc
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    async def search_contacts(self, access_token: str, query: ContactSearchQuery) -> list[Contact]:
        result = await self._request(
            "GET",
            access_token,
            "/people/me/connections",
            params={"personFields": _PERSON_FIELDS, "pageSize": _MAX_LIST_PAGE_SIZE},
        )
        contacts = [_parse_person(raw) for raw in result.get("connections", [])]
        if query.query:
            needle = query.query.strip().lower()
            contacts = [c for c in contacts if _matches(c, needle)]
        return contacts[: query.limit]

    async def get_contact(self, access_token: str, resource_name: str) -> Contact:
        _validate_resource_name(resource_name)
        raw = await self._request(
            "GET", access_token, f"/{resource_name}", params={"personFields": _PERSON_FIELDS}
        )
        return _parse_person(raw)

    async def create_contact(self, access_token: str, contact: NewContact) -> Contact:
        body = {
            "names": [{"givenName": contact.given_name, "familyName": contact.family_name}],
            "emailAddresses": [{"value": address} for address in contact.emails],
            "phoneNumbers": [{"value": number} for number in contact.phones],
        }
        raw = await self._request("POST", access_token, "/people:createContact", json=body)
        return _parse_person(raw)

    async def update_contact(self, access_token: str, resource_name: str, update: ContactUpdate) -> Contact:
        # The People API requires the current etag for optimistic-concurrency
        # updates — fetch it first, then send exactly the fields being changed.
        current = await self.get_contact(access_token, resource_name)
        body: dict = {"etag": current.etag}
        update_fields = []
        if update.given_name is not None or update.family_name is not None:
            body["names"] = [
                {
                    "givenName": update.given_name if update.given_name is not None else current.given_name,
                    "familyName": update.family_name if update.family_name is not None else current.family_name,
                }
            ]
            update_fields.append("names")
        if update.emails is not None:
            body["emailAddresses"] = [{"value": address} for address in update.emails]
            update_fields.append("emailAddresses")
        if update.phones is not None:
            body["phoneNumbers"] = [{"value": number} for number in update.phones]
            update_fields.append("phoneNumbers")

        raw = await self._request(
            "PATCH",
            access_token,
            f"/{resource_name}:updateContact",
            params={"updatePersonFields": ",".join(update_fields) or "names"},
            json=body,
        )
        return _parse_person(raw)

    async def delete_contact(self, access_token: str, resource_name: str) -> None:
        _validate_resource_name(resource_name)
        await self._request("DELETE", access_token, f"/{resource_name}:deleteContact")


def _matches(contact: Contact, needle: str) -> bool:
    haystack = " ".join([contact.display_name, contact.given_name, contact.family_name, *contact.emails, *contact.phones])
    return needle in haystack.lower()


def _parse_person(raw: dict) -> Contact:
    names = raw.get("names", []) or []
    name = names[0] if names else {}
    return Contact(
        resource_name=raw.get("resourceName", ""),
        etag=raw.get("etag", ""),
        display_name=name.get("displayName", ""),
        given_name=name.get("givenName", ""),
        family_name=name.get("familyName", ""),
        emails=[e["value"] for e in raw.get("emailAddresses", []) if e.get("value")],
        phones=[p["value"] for p in raw.get("phoneNumbers", []) if p.get("value")],
    )
