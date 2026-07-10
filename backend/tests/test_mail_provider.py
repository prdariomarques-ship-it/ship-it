"""GmailProvider — REST via httpx, no SDK. Mirrors the mocking style already
used for the Gemini LLM provider (`tests/test_providers.py`): patch
`httpx.AsyncClient` at the module it's imported into.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.mail.base import EmailSearchQuery, MailProviderError
from providers.mail.factory import UnknownMailProviderError, get_mail_provider
from providers.mail.gmail.provider import GmailProvider, _build_search_query, _extract_body
from utils.config import get_settings


def _mock_response(json_body: dict) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=json_body)
    return response


def _patch_client(get_result=None, post_result=None):
    """`get_result`: a single response (returned every call) or a list of
    responses (one per successive `client.get` call, in order)."""
    client = MagicMock()
    if get_result is not None:
        client.get = AsyncMock(side_effect=get_result if isinstance(get_result, list) else [get_result] * 20)
    if post_result is not None:
        client.post = AsyncMock(return_value=post_result)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return patch("providers.mail.gmail.provider.httpx.AsyncClient", return_value=client), client


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "client-id")
    monkeypatch.setattr(get_settings(), "google_client_secret", "client-secret")
    monkeypatch.setattr(get_settings(), "google_redirect_uri", "https://app.example.com/api/mail/oauth/callback")
    return GmailProvider()


# --- authorization_url --------------------------------------------------------
def test_authorization_url_includes_offline_access_and_state(provider):
    url = provider.authorization_url("the-state-token")
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "state=the-state-token" in url
    assert "client_id=client-id" in url
    assert "gmail.readonly" in url


# --- OAuth token exchange ------------------------------------------------------
@pytest.mark.asyncio
async def test_exchange_code_returns_tokens(provider):
    body = {"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600, "scope": "gmail.readonly"}
    patcher, client = _patch_client(post_result=_mock_response(body))
    with patcher:
        tokens = await provider.exchange_code("auth-code")
    assert tokens.access_token == "at1"
    assert tokens.refresh_token == "rt1"
    client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_access_token_preserves_the_original_refresh_token(provider):
    """Google's refresh grant doesn't repeat the refresh_token in its response."""
    body = {"access_token": "at2", "expires_in": 3600, "scope": "gmail.readonly"}
    patcher, _ = _patch_client(post_result=_mock_response(body))
    with patcher:
        tokens = await provider.refresh_access_token("original-refresh-token")
    assert tokens.access_token == "at2"
    assert tokens.refresh_token == "original-refresh-token"


@pytest.mark.asyncio
async def test_token_request_http_failure_raises_mail_provider_error(provider):
    import httpx as httpx_module

    client = MagicMock()
    client.post = AsyncMock(side_effect=httpx_module.ConnectError("down"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch("providers.mail.gmail.provider.httpx.AsyncClient", return_value=client):
        with pytest.raises(MailProviderError):
            await provider.exchange_code("auth-code")


# --- search --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_lists_then_fetches_metadata_for_each_message(provider):
    list_body = {"messages": [{"id": "m1"}, {"id": "m2"}]}
    detail_body = {
        "id": "m1",
        "threadId": "t1",
        "snippet": "oi",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "a@example.com"},
                {"name": "Subject", "value": "Assunto"},
                {"name": "Date", "value": "Mon, 01 Jul 2026 10:00:00 +0000"},
            ]
        },
    }
    patcher, client = _patch_client(get_result=[_mock_response(list_body), _mock_response(detail_body), _mock_response(detail_body)])
    with patcher:
        messages = await provider.search("access-token", EmailSearchQuery(sender="a@example.com", limit=10))
    assert len(messages) == 2
    assert messages[0].sender == "a@example.com"
    assert messages[0].subject == "Assunto"
    assert messages[0].body == ""  # search never fetches the body


@pytest.mark.asyncio
async def test_search_api_failure_raises_mail_provider_error(provider):
    import httpx as httpx_module

    client = MagicMock()
    client.get = AsyncMock(side_effect=httpx_module.ConnectError("down"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch("providers.mail.gmail.provider.httpx.AsyncClient", return_value=client):
        with pytest.raises(MailProviderError):
            await provider.search("access-token", EmailSearchQuery())


# --- get_thread ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_thread_parses_all_messages_and_extracts_plain_text_body(provider):
    import base64

    body_text = base64.urlsafe_b64encode("Olá, tudo bem?".encode()).decode()
    thread_body = {
        "messages": [
            {
                "id": "m1",
                "threadId": "t1",
                "snippet": "s",
                "payload": {
                    "mimeType": "text/plain",
                    "body": {"data": body_text},
                    "headers": [
                        {"name": "From", "value": "a@example.com"},
                        {"name": "Subject", "value": "Assunto Original"},
                    ],
                },
            }
        ]
    }
    patcher, _ = _patch_client(get_result=[_mock_response(thread_body)])
    with patcher:
        thread = await provider.get_thread("access-token", "t1")
    assert thread.subject == "Assunto Original"
    assert len(thread.messages) == 1
    assert thread.messages[0].body == "Olá, tudo bem?"


@pytest.mark.asyncio
async def test_get_thread_url_encodes_the_thread_id(provider):
    """`thread_id` comes straight from a tool argument (`read_email_thread`/
    `summarize_email_thread`) — a model-supplied value containing `/` must
    never change which Gmail API path segment gets requested (path
    traversal within Gmail's own API surface, e.g. `.../threads/x/../drafts/y`
    resolving to a completely different resource than "threads")."""
    patcher, client = _patch_client(get_result=[_mock_response({"messages": []})])
    with patcher:
        await provider.get_thread("access-token", "abc/../../drafts/xyz")
    requested_url = client.get.call_args.args[0]
    assert "/threads/abc%2F..%2F..%2Fdrafts%2Fxyz" in requested_url
    assert "/threads/abc/../../drafts/xyz" not in requested_url


def test_extract_body_prefers_text_plain_over_html_fallback():
    import base64

    plain = base64.urlsafe_b64encode(b"plain text").decode()
    html = base64.urlsafe_b64encode(b"<p>html</p>").decode()
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": html}},
            {"mimeType": "text/plain", "body": {"data": plain}},
        ],
    }
    assert _extract_body(payload) == "plain text"


def test_extract_body_falls_back_to_html_when_no_plain_text_part():
    import base64

    html = base64.urlsafe_b64encode(b"<p>html only</p>").decode()
    payload = {"mimeType": "multipart/alternative", "parts": [{"mimeType": "text/html", "body": {"data": html}}]}
    assert _extract_body(payload) == "<p>html only</p>"


# --- query building --------------------------------------------------------------
def test_build_search_query_combines_all_fields_with_and_semantics():
    from datetime import datetime, timezone

    query = EmailSearchQuery(
        sender="a@example.com",
        subject="Proposta",
        since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        until=datetime(2026, 2, 1, tzinfo=timezone.utc),
        labels=["IMPORTANT"],
        keywords="orçamento",
    )
    built = _build_search_query(query)
    assert "from:a@example.com" in built
    assert 'subject:"Proposta"' in built
    assert "after:2026/01/01" in built
    assert "before:2026/02/01" in built
    assert "label:IMPORTANT" in built
    assert "orçamento" in built


def test_build_search_query_empty_when_nothing_provided():
    assert _build_search_query(EmailSearchQuery()) == ""


# --- factory ------------------------------------------------------------------
def test_mail_factory_resolves_gmail_by_default():
    get_mail_provider.cache_clear()
    assert isinstance(get_mail_provider(), GmailProvider)
    get_mail_provider.cache_clear()


def test_mail_factory_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(get_settings(), "mail_provider", "not-a-real-provider")
    get_mail_provider.cache_clear()
    with pytest.raises(UnknownMailProviderError):
        get_mail_provider()
    monkeypatch.setattr(get_settings(), "mail_provider", "gmail")
    get_mail_provider.cache_clear()
