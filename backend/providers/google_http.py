"""Shared HTTP helper for every Google-backed provider (Gmail, Calendar,
Contacts, Drive). These four providers live in separate domain packages
(no common ABC to hang this on, unlike WhatsApp's `providers/whatsapp/base.py`),
but they all talk to the same vendor and fail the same transient way, so the
retry/backoff logic is factored out here instead of copy-pasted four times.

Mirrors `providers/whatsapp/base.py::_request`'s contract: exponential
backoff across `max_attempts`, one shared metric family. Extends it with
one Google-specific behavior — a `Retry-After` header (sent by Google on
429/503) overrides the computed backoff, since the vendor is telling us
exactly how long to wait.

Callers keep their own try/except around this (to log a domain-specific
message and raise their own `MailProviderError`/`CalendarProviderError`/
`ContactsProviderError`/`DriveProviderError`) — this helper only retries
and re-raises the last `httpx.HTTPError` for them to catch.
"""

import asyncio

import httpx

from observability.metrics import record_google_request
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


async def google_request(
    provider: str,
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    json: dict | None = None,
    data: dict | None = None,
    timeout: float = 30,
    max_attempts: int | None = None,
) -> httpx.Response:
    settings = get_settings()
    max_attempts = (
        max_attempts
        if max_attempts is not None
        else settings.google_request_max_attempts
    )
    last_exc: httpx.HTTPError | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method, url, headers=headers, params=params, json=json, data=data
                )
                response.raise_for_status()
            record_google_request(provider, "ok")
            return response
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            backoff = _backoff_seconds(exc, attempt, settings)
            logger.warning(
                "%s API call failed (%s %s), attempt %s/%s, retrying in %ss: %s",
                provider,
                method,
                url,
                attempt,
                max_attempts,
                backoff,
                exc,
            )
            await asyncio.sleep(backoff)

    record_google_request(provider, "error")
    if last_exc is None:
        # Only reachable if max_attempts <= 0 (the loop never ran, so the
        # except branch that sets last_exc never did either) — not a normal
        # retry exhaustion, a misconfiguration.
        raise ValueError(
            f"google_request called with max_attempts={max_attempts}; must be >= 1"
        )
    raise last_exc


def _backoff_seconds(exc: httpx.HTTPError, attempt: int, settings) -> float:
    response = getattr(exc, "response", None)
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
    return settings.google_request_backoff_seconds * (2 ** (attempt - 1))
