"""Shared retry/backoff helper for the Google-backed providers (Gmail,
Calendar, Contacts, Drive). Mirrors the test style used for
`providers/whatsapp/base.py::_request` in `tests/test_providers.py`.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from providers.google_http import (
    GoogleCircuitOpenError,
    google_request,
    open_circuit_providers,
)
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


# --- Circuit breaker: Release 1.6, M2 platform reliability -----------------------------------


def _failing_client() -> MagicMock:
    client = MagicMock()
    client.request = AsyncMock(side_effect=httpx.ConnectError("down"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _succeeding_client() -> MagicMock:
    client = MagicMock()
    client.request = AsyncMock(return_value=_json_response())
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_consecutive_failures(monkeypatch):
    from observability.metrics import GOOGLE_CIRCUIT_STATE

    settings = get_settings()
    monkeypatch.setattr(settings, "google_request_max_attempts", 1)
    monkeypatch.setattr(settings, "google_request_backoff_seconds", 0)
    monkeypatch.setattr(settings, "google_circuit_failure_threshold", 3)
    monkeypatch.setattr(settings, "google_circuit_reset_seconds", 999)

    client = _failing_client()
    with patch("providers.google_http.httpx.AsyncClient", return_value=client):
        for _ in range(3):
            with pytest.raises(httpx.ConnectError):
                await google_request("gmail", "GET", "https://example.test/x")

    assert "gmail" in open_circuit_providers()
    assert GOOGLE_CIRCUIT_STATE.labels("gmail")._value.get() == 1
    assert client.request.await_count == 3

    # A 4th call must fail fast -- no new request attempted at all.
    with patch("providers.google_http.httpx.AsyncClient", return_value=client):
        with pytest.raises(GoogleCircuitOpenError) as exc_info:
            await google_request("gmail", "GET", "https://example.test/x")
    assert client.request.await_count == 3  # unchanged -- no 4th attempt made
    assert exc_info.value.provider == "gmail"
    assert exc_info.value.retry_after_seconds > 0


def test_circuit_open_error_is_an_httpx_http_error():
    """Every existing call site across the four providers catches
    `except httpx.HTTPError` -- the breaker must be transparently caught
    there with zero changes needed at those call sites."""
    assert isinstance(GoogleCircuitOpenError("gmail", 30.0), httpx.HTTPError)


@pytest.mark.asyncio
async def test_circuit_half_open_probe_success_closes_circuit(monkeypatch):
    from observability.metrics import GOOGLE_CIRCUIT_STATE

    settings = get_settings()
    monkeypatch.setattr(settings, "google_request_max_attempts", 1)
    monkeypatch.setattr(settings, "google_request_backoff_seconds", 0)
    monkeypatch.setattr(settings, "google_circuit_failure_threshold", 2)
    monkeypatch.setattr(settings, "google_circuit_reset_seconds", 30)

    now = [0.0]
    monkeypatch.setattr("providers.google_http.time.monotonic", lambda: now[0])

    failing = _failing_client()
    with patch("providers.google_http.httpx.AsyncClient", return_value=failing):
        for _ in range(2):
            with pytest.raises(httpx.ConnectError):
                await google_request("google_calendar", "GET", "https://example.test/x")
    assert "google_calendar" in open_circuit_providers()

    now[0] += 31  # cooldown elapsed

    succeeding = _succeeding_client()
    with patch("providers.google_http.httpx.AsyncClient", return_value=succeeding):
        response = await google_request("google_calendar", "GET", "https://example.test/x")

    assert response is not None
    assert "google_calendar" not in open_circuit_providers()
    assert GOOGLE_CIRCUIT_STATE.labels("google_calendar")._value.get() == 0

    # Circuit is closed again -- a normal call proceeds without being blocked.
    with patch("providers.google_http.httpx.AsyncClient", return_value=succeeding):
        await google_request("google_calendar", "GET", "https://example.test/x")


@pytest.mark.asyncio
async def test_circuit_half_open_probe_failure_reopens_circuit(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_request_max_attempts", 1)
    monkeypatch.setattr(settings, "google_request_backoff_seconds", 0)
    monkeypatch.setattr(settings, "google_circuit_failure_threshold", 1)
    monkeypatch.setattr(settings, "google_circuit_reset_seconds", 30)

    now = [0.0]
    monkeypatch.setattr("providers.google_http.time.monotonic", lambda: now[0])

    failing = _failing_client()
    with patch("providers.google_http.httpx.AsyncClient", return_value=failing):
        with pytest.raises(httpx.ConnectError):
            await google_request("google_drive", "GET", "https://example.test/x")
    assert "google_drive" in open_circuit_providers()

    # Still within cooldown -- must fail fast, no request attempted at all.
    with patch("providers.google_http.httpx.AsyncClient", return_value=failing):
        with pytest.raises(GoogleCircuitOpenError):
            await google_request("google_drive", "GET", "https://example.test/x")
    assert failing.request.await_count == 1  # only the original failure, no 2nd attempt

    now[0] += 31  # cooldown elapsed -- next call is the probe, and it fails too

    with patch("providers.google_http.httpx.AsyncClient", return_value=failing):
        with pytest.raises(httpx.ConnectError):
            await google_request("google_drive", "GET", "https://example.test/x")
    assert failing.request.await_count == 2
    assert "google_drive" in open_circuit_providers()

    # Freshly re-opened -- immediately still within the (new) cooldown, so
    # the call right after must fail fast again, not attempt a 2nd probe.
    with patch("providers.google_http.httpx.AsyncClient", return_value=failing):
        with pytest.raises(GoogleCircuitOpenError):
            await google_request("google_drive", "GET", "https://example.test/x")
    assert failing.request.await_count == 2  # unchanged


@pytest.mark.asyncio
async def test_circuit_concurrent_calls_during_half_open_only_one_probe_reaches_client(
    monkeypatch,
):
    import asyncio

    settings = get_settings()
    monkeypatch.setattr(settings, "google_request_max_attempts", 1)
    monkeypatch.setattr(settings, "google_request_backoff_seconds", 0)
    monkeypatch.setattr(settings, "google_circuit_failure_threshold", 1)
    monkeypatch.setattr(settings, "google_circuit_reset_seconds", 30)

    now = [0.0]
    monkeypatch.setattr("providers.google_http.time.monotonic", lambda: now[0])

    failing = _failing_client()
    with patch("providers.google_http.httpx.AsyncClient", return_value=failing):
        with pytest.raises(httpx.ConnectError):
            await google_request("google_contacts", "GET", "https://example.test/x")
    assert "google_contacts" in open_circuit_providers()

    now[0] += 31  # cooldown elapsed

    release_probe = asyncio.Event()
    probe_client = MagicMock()

    async def _blocked_request(*args, **kwargs):
        await release_probe.wait()
        return _json_response()

    probe_client.request = AsyncMock(side_effect=_blocked_request)
    probe_client.__aenter__ = AsyncMock(return_value=probe_client)
    probe_client.__aexit__ = AsyncMock(return_value=False)

    with patch("providers.google_http.httpx.AsyncClient", return_value=probe_client):
        probe_task = asyncio.create_task(
            google_request("google_contacts", "GET", "https://example.test/x")
        )
        await asyncio.sleep(0)  # let the probe task reach the blocked client call

        # A second call arriving while the probe is still in flight must
        # fail fast, not queue up as a second probe.
        with pytest.raises(GoogleCircuitOpenError):
            await google_request("google_contacts", "GET", "https://example.test/x")

        release_probe.set()
        await probe_task

    assert probe_client.request.await_count == 1
    assert "google_contacts" not in open_circuit_providers()  # the probe succeeded


@pytest.mark.asyncio
async def test_successful_call_resets_consecutive_failure_count(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_request_max_attempts", 1)
    monkeypatch.setattr(settings, "google_request_backoff_seconds", 0)
    monkeypatch.setattr(settings, "google_circuit_failure_threshold", 3)
    monkeypatch.setattr(settings, "google_circuit_reset_seconds", 999)

    failing = _failing_client()
    succeeding = _succeeding_client()

    with patch("providers.google_http.httpx.AsyncClient", return_value=failing):
        for _ in range(2):
            with pytest.raises(httpx.ConnectError):
                await google_request("gmail", "GET", "https://example.test/x")
    with patch("providers.google_http.httpx.AsyncClient", return_value=succeeding):
        await google_request("gmail", "GET", "https://example.test/x")  # resets the count

    with patch("providers.google_http.httpx.AsyncClient", return_value=failing):
        for _ in range(2):
            with pytest.raises(httpx.ConnectError):
                await google_request("gmail", "GET", "https://example.test/x")
    assert "gmail" not in open_circuit_providers()  # only 2 since the reset, threshold is 3

    with patch("providers.google_http.httpx.AsyncClient", return_value=failing):
        with pytest.raises(httpx.ConnectError):
            await google_request("gmail", "GET", "https://example.test/x")
    assert "gmail" in open_circuit_providers()  # 3rd since the reset


@pytest.mark.asyncio
async def test_circuit_state_is_independent_per_provider(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_request_max_attempts", 1)
    monkeypatch.setattr(settings, "google_request_backoff_seconds", 0)
    monkeypatch.setattr(settings, "google_circuit_failure_threshold", 1)
    monkeypatch.setattr(settings, "google_circuit_reset_seconds", 999)

    failing = _failing_client()
    with patch("providers.google_http.httpx.AsyncClient", return_value=failing):
        with pytest.raises(httpx.ConnectError):
            await google_request("gmail", "GET", "https://example.test/x")

    assert open_circuit_providers() == ["gmail"]

    succeeding = _succeeding_client()
    with patch("providers.google_http.httpx.AsyncClient", return_value=succeeding):
        response = await google_request(
            "google_calendar", "GET", "https://example.test/x"
        )
    assert response is not None
    assert open_circuit_providers() == ["gmail"]  # google_calendar unaffected
