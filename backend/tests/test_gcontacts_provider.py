"""GoogleContactsProvider (People API) — REST via httpx, no SDK."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.contacts.base import (
    ContactSearchQuery,
    ContactsProviderError,
    ContactUpdate,
    NewContact,
)
from providers.contacts.factory import (
    UnknownContactsProviderError,
    get_contacts_provider,
)
from providers.contacts.google.provider import GoogleContactsProvider, _parse_person
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
        "google_contacts_redirect_uri",
        "https://app.example.com/api/gcontacts/oauth/callback",
    )
    return GoogleContactsProvider()


def test_authorization_url_includes_offline_access_full_scope_and_state(provider):
    url = provider.authorization_url("the-state-token")
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "state=the-state-token" in url
    assert "auth%2Fcontacts" in url


@pytest.mark.asyncio
async def test_exchange_code_returns_tokens(provider):
    body = {
        "access_token": "at1",
        "refresh_token": "rt1",
        "expires_in": 3600,
        "scope": "contacts",
    }
    patcher, _ = _patch_client(post_result=_mock_response(body))
    with patcher:
        tokens = await provider.exchange_code("auth-code")
    assert tokens.access_token == "at1"
    assert tokens.refresh_token == "rt1"


@pytest.mark.asyncio
async def test_refresh_access_token_preserves_the_original_refresh_token(provider):
    body = {"access_token": "at2", "expires_in": 3600, "scope": "contacts"}
    patcher, _ = _patch_client(post_result=_mock_response(body))
    with patcher:
        tokens = await provider.refresh_access_token("original-refresh-token")
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
        with pytest.raises(ContactsProviderError):
            await provider.exchange_code("auth-code")


def _person(resource_name, given, family="", emails=None, phones=None, etag="etag-1"):
    return {
        "resourceName": resource_name,
        "etag": etag,
        "names": [
            {
                "givenName": given,
                "familyName": family,
                "displayName": f"{given} {family}".strip(),
            }
        ],
        "emailAddresses": [{"value": e} for e in (emails or [])],
        "phoneNumbers": [{"value": p} for p in (phones or [])],
    }


@pytest.mark.asyncio
async def test_search_contacts_lists_everyone_without_a_query(provider):
    body = {"connections": [_person("people/c1", "Ana"), _person("people/c2", "Beto")]}
    patcher, _ = _patch_client(request_result=[_mock_response(body)])
    with patcher:
        contacts = await provider.search_contacts("access-token", ContactSearchQuery())
    assert len(contacts) == 2


@pytest.mark.asyncio
async def test_search_contacts_filters_client_side_by_name(provider):
    body = {
        "connections": [
            _person("people/c1", "Ana", emails=["ana@example.com"]),
            _person("people/c2", "Beto"),
        ]
    }
    patcher, _ = _patch_client(request_result=[_mock_response(body)])
    with patcher:
        contacts = await provider.search_contacts(
            "access-token", ContactSearchQuery(query="ana")
        )
    assert len(contacts) == 1
    assert contacts[0].given_name == "Ana"


@pytest.mark.asyncio
async def test_search_contacts_filters_by_phone_or_email_substring(provider):
    body = {
        "connections": [
            _person("people/c1", "Ana", phones=["+5511999990000"]),
            _person("people/c2", "Beto", emails=["beto@example.com"]),
        ]
    }
    patcher, _ = _patch_client(
        request_result=[_mock_response(body), _mock_response(body)]
    )
    with patcher:
        by_phone = await provider.search_contacts(
            "access-token", ContactSearchQuery(query="999990000")
        )
        by_email = await provider.search_contacts(
            "access-token", ContactSearchQuery(query="beto@")
        )
    assert [c.given_name for c in by_phone] == ["Ana"]
    assert [c.given_name for c in by_email] == ["Beto"]


@pytest.mark.asyncio
async def test_get_contact_returns_etag_needed_for_updates(provider):
    patcher, _ = _patch_client(
        request_result=[_mock_response(_person("people/c1", "Ana", etag="etag-xyz"))]
    )
    with patcher:
        contact = await provider.get_contact("access-token", "people/c1")
    assert contact.etag == "etag-xyz"


@pytest.mark.asyncio
async def test_get_contact_rejects_a_resource_name_with_a_path_traversal_attempt(
    provider,
):
    """`resource_name` comes straight from a tool argument
    (`update_google_contact`/`delete_google_contact`) and legitimately
    contains a literal '/' (People API format is "people/<id>"), so it
    can't be `quote()`d like Gmail's thread_id or Drive's file_id without
    breaking the normal case — validated against an allowlist instead. A
    value like "people/c1/../otherContacts/x" must be rejected before ever
    reaching a URL, not silently sent to a different People API path."""
    client = MagicMock()
    client.request = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "providers.google_http.httpx.AsyncClient", return_value=client
    ):
        with pytest.raises(ContactsProviderError):
            await provider.get_contact("access-token", "people/c1/../otherContacts/x")
    client.request.assert_not_awaited()  # rejected before any request was made


@pytest.mark.asyncio
async def test_delete_contact_rejects_an_invalid_resource_name(provider):
    client = MagicMock()
    client.request = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "providers.google_http.httpx.AsyncClient", return_value=client
    ):
        with pytest.raises(ContactsProviderError):
            await provider.delete_contact("access-token", "people/c1?admin=true")
    client.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_contact_rejects_an_invalid_resource_name_before_fetching_the_etag(
    provider,
):
    client = MagicMock()
    client.request = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch(
        "providers.google_http.httpx.AsyncClient", return_value=client
    ):
        with pytest.raises(ContactsProviderError):
            await provider.update_contact(
                "access-token",
                "otherContacts/../people/c1",
                ContactUpdate(given_name="X"),
            )
    client.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_contact_accepts_the_special_people_me_resource_name(provider):
    """`gcontacts/router.py::_resolve_account_label` relies on this exact
    value (a Google-documented special resource, not user input) staying
    valid after the allowlist was introduced."""
    patcher, _ = _patch_client(
        request_result=[_mock_response(_person("people/me", "Dario"))]
    )
    with patcher:
        contact = await provider.get_contact("access-token", "people/me")
    assert contact.given_name == "Dario"


@pytest.mark.asyncio
async def test_create_contact_sends_expected_body(provider):
    response_body = _person(
        "people/new", "Carlos", emails=["c@example.com"], phones=["123"]
    )
    patcher, client = _patch_client(request_result=[_mock_response(response_body)])
    new_contact = NewContact(
        given_name="Carlos", emails=["c@example.com"], phones=["123"]
    )
    with patcher:
        contact = await provider.create_contact("access-token", new_contact)
    assert contact.given_name == "Carlos"
    sent_body = client.request.call_args.kwargs["json"]
    assert sent_body["names"] == [{"givenName": "Carlos", "familyName": ""}]
    assert sent_body["emailAddresses"] == [{"value": "c@example.com"}]


@pytest.mark.asyncio
async def test_update_contact_fetches_etag_first_then_patches(provider):
    """The People API requires the current etag for optimistic-concurrency
    updates — the provider must GET before PATCH."""
    current = _person("people/c1", "Ana", etag="etag-current")
    updated = _person("people/c1", "Ana Maria", etag="etag-new")
    patcher, client = _patch_client(
        request_result=[_mock_response(current), _mock_response(updated)]
    )
    update = ContactUpdate(given_name="Ana Maria")
    with patcher:
        contact = await provider.update_contact("access-token", "people/c1", update)
    assert contact.given_name == "Ana Maria"
    assert client.request.call_count == 2
    first_call, second_call = client.request.call_args_list
    assert first_call.args[0] == "GET"
    assert second_call.args[0] == "PATCH"
    assert second_call.kwargs["json"]["etag"] == "etag-current"


@pytest.mark.asyncio
async def test_update_contact_only_changes_requested_fields(provider):
    current = _person(
        "people/c1", "Ana", family="Silva", emails=["ana@old.com"], etag="etag-current"
    )
    updated = _person(
        "people/c1", "Ana", family="Silva", emails=["ana@new.com"], etag="etag-new"
    )
    patcher, client = _patch_client(
        request_result=[_mock_response(current), _mock_response(updated)]
    )
    update = ContactUpdate(emails=["ana@new.com"])
    with patcher:
        await provider.update_contact("access-token", "people/c1", update)
    second_call = client.request.call_args_list[1]
    assert "names" not in second_call.kwargs["json"]
    assert second_call.kwargs["json"]["emailAddresses"] == [{"value": "ana@new.com"}]


@pytest.mark.asyncio
async def test_delete_contact_calls_delete(provider):
    patcher, client = _patch_client(
        request_result=[_mock_response({}, status_code=204)]
    )
    with patcher:
        result = await provider.delete_contact("access-token", "people/c1")
    assert result is None
    assert client.request.call_args.args[0] == "DELETE"


def test_parse_person_handles_missing_fields():
    contact = _parse_person({"resourceName": "people/bare"})
    assert contact.given_name == ""
    assert contact.emails == []


def test_contacts_factory_resolves_google_by_default():
    get_contacts_provider.cache_clear()
    assert isinstance(get_contacts_provider(), GoogleContactsProvider)
    get_contacts_provider.cache_clear()


def test_contacts_factory_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(get_settings(), "contacts_provider", "not-a-real-provider")
    get_contacts_provider.cache_clear()
    with pytest.raises(UnknownContactsProviderError):
        get_contacts_provider()
    monkeypatch.setattr(get_settings(), "contacts_provider", "google")
    get_contacts_provider.cache_clear()
