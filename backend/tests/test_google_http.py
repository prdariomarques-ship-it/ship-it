"""Shared retry/backoff helper for the Google-backed providers (Gmail,
Calendar, Contacts, Drive). Mirrors the test style used for
`providers/whatsapp/base.py::_request` in `tests/test_providers.py`.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from providers.google_http import google_request
from utils.config import get_settings


def _json_response(status_code: int = 200, headers: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    response.raise_for_status = MagicMock()
    return response


def _http_status_error(status_code: int, headers: dict | None = None) -> httpx.HTTPStatusError:
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    return httpx.HTTPStatusError("error", request=MagicMock(), response=response)


@pytest.mark.asyncio
async def test_retries_transient_failures_then_succeeds(monkeypatch):
    from observability.metrics import GOOGLE_PROVIDER_REQUESTS

    settings = get_settings()
    monkeypatch.setattr(settings, "google_request_max_attempts", 3)
    monkeypatch.setattr(settings, "google_request_backoff_seconds", 0)

    success = _json_response()
    client = MagicMock()
    client.request = AsyncMock(
        side_effect=[httpx.ConnectError("down"), httpx.ConnectError("down"), success]
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    before = GOOGLE_PROVIDER_REQUESTS.labels("gmail", "ok")._value.get()
    with patch("providers.google_http.httpx.AsyncClient", return_value=client):
        response = await google_request("gmail", "GET", "https://example.test/x")

    assert response is success
    assert client.request.await_count == 3
    assert GOOGLE_PROVIDER_REQUESTS.labels("gmail", "ok")._value.get() == before + 1


@pytest.mark.asyncio
async def test_raises_after_exhausting_all_retries(monkeypatch):
    from observability.metrics import GOOGLE_PROVIDER_REQUESTS

    settings = get_settings()
    monkeypatch.setattr(settings, "google_request_max_attempts", 2)
    monkeypatch.setattr(settings, "google_request_backoff_seconds", 0)

    client = MagicMock()
    client.request = AsyncMock(side_effect=httpx.ConnectError("gateway down"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    before = GOOGLE_PROVIDER_REQUESTS.labels("google_calendar", "error")._value.get()
    with patch("providers.google_http.httpx.AsyncClient", return_value=client):
        with pytest.raises(httpx.ConnectError):
            await google_request("google_calendar", "GET", "https://example.test/x")

    assert client.request.await_count == 2
    assert (
        GOOGLE_PROVIDER_REQUESTS.labels("google_calendar", "error")._value.get()
        == before + 1
    )


@pytest.mark.asyncio
async def test_respects_retry_after_header_over_computed_backoff(monkeypatch):
    """A 429/503 telling us exactly how long to wait must override the
    exponential formula, not be added to it."""
    settings = get_settings()
    monkeypatch.setattr(settings, "google_request_max_attempts", 2)
    monkeypatch.setattr(settings, "google_request_backoff_seconds", 999)

    sleep_calls = []

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)

    rate_limited = _http_status_error(429, headers={"Retry-After": "7"})
    success = _json_response()
    client = MagicMock()
    client.request = AsyncMock(side_effect=[rate_limited, success])
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("providers.google_http.httpx.AsyncClient", return_value=client),
        patch("providers.google_http.asyncio.sleep", _fake_sleep),
    ):
        response = await google_request("google_drive", "GET", "https://example.test/x")

    assert response is success
    assert sleep_calls == [7.0]


@pytest.mark.asyncio
async def test_ignores_a_malformed_retry_after_header_and_falls_back_to_backoff(
    monkeypatch,
):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_request_max_attempts", 2)
    monkeypatch.setattr(settings, "google_request_backoff_seconds", 1.5)

    sleep_calls = []

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)

    rate_limited = _http_status_error(503, headers={"Retry-After": "not-a-number"})
    success = _json_response()
    client = MagicMock()
    client.request = AsyncMock(side_effect=[rate_limited, success])
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("providers.google_http.httpx.AsyncClient", return_value=client),
        patch("providers.google_http.asyncio.sleep", _fake_sleep),
    ):
        await google_request("google_contacts", "GET", "https://example.test/x")

    assert sleep_calls == [1.5]


@pytest.mark.asyncio
async def test_max_attempts_override_skips_retry(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_request_max_attempts", 5)
    monkeypatch.setattr(settings, "google_request_backoff_seconds", 0)

    client = MagicMock()
    client.request = AsyncMock(side_effect=httpx.ConnectError("down"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("providers.google_http.httpx.AsyncClient", return_value=client):
        with pytest.raises(httpx.ConnectError):
            await google_request(
                "gmail", "GET", "https://example.test/x", max_attempts=1
            )

    assert client.request.await_count == 1


@pytest.mark.asyncio
async def test_max_attempts_zero_raises_a_clear_error_not_a_bare_none():
    """max_attempts<=0 means the loop never runs, so the retry-tracking
    variable never gets set — previously this fell through to `raise None`,
    a confusing TypeError instead of a message pointing at the actual
    misconfiguration."""
    with pytest.raises(ValueError, match="max_attempts=0"):
        await google_request(
            "gmail", "GET", "https://example.test/x", max_attempts=0
        )
