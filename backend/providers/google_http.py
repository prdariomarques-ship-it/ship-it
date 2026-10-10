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

Also implements a per-provider circuit breaker (Release 1.6, M2 platform
reliability): after `google_circuit_failure_threshold` consecutive
exhausted-retry failures, further calls fail immediately with
`GoogleCircuitOpenError` (no HTTP call, no retries) for
`google_circuit_reset_seconds`, then one probe call is let through
half-open. This exists purely to stop every caller from repeating the same
doomed 3-attempt retry-with-backoff dance during a sustained Google outage
-- it changes nothing about a single successful or transiently-failing
call. Circuit state is in-process only (per worker, like everything else
in this codebase -- see docs/architecture.md's "no central StateManager"
principle); it is not shared or persisted across processes/restarts.
"""

import asyncio
import time
from dataclasses import dataclass

import httpx

from observability.metrics import record_google_circuit_state, record_google_request
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class GoogleCircuitOpenError(httpx.HTTPError):
    """Raised instead of attempting a request when a provider's circuit
    breaker is open -- fails fast (no HTTP call, no retries) rather than
    repeating the same doomed retry-with-backoff dance for every caller
    during a sustained outage. Subclasses httpx.HTTPError deliberately: every
    existing `except httpx.HTTPError` at the four call sites (Calendar/Gmail/
    Contacts/Drive) already wraps a failure into its own domain error, and
    this should be caught and handled identically there, with zero changes
    needed at those call sites."""

    def __init__(self, provider: str, retry_after_seconds: float) -> None:
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"{provider}: circuit open, too many consecutive failures -- "
            f"failing fast for {retry_after_seconds:.0f}s more"
        )


@dataclass
class _CircuitState:
    consecutive_failures: int = 0
    opened_at: float | None = None  # time.monotonic() when the circuit opened
    probe_in_flight: bool = False


_circuits: dict[str, _CircuitState] = {}


def _circuit_for(provider: str) -> _CircuitState:
    return _circuits.setdefault(provider, _CircuitState())


def open_circuit_providers() -> list[str]:
    """Providers currently fast-failing (circuit open) -- used by the
    readiness check (observability/health.py) to surface Google integration
    health without making a real network call itself."""
    return [name for name, state in _circuits.items() if state.opened_at is not None]


def _check_circuit(provider: str, settings) -> None:
    """Raise GoogleCircuitOpenError if the circuit is open and the cooldown
    hasn't elapsed. Once the cooldown elapses, allow exactly one probe
    request through (half-open) -- concurrent callers during that window
    still fail fast rather than piling on a service that may still be down."""
    circuit = _circuit_for(provider)
    if circuit.opened_at is None:
        return

    elapsed = time.monotonic() - circuit.opened_at
    remaining = settings.google_circuit_reset_seconds - elapsed
    if remaining <= 0 and not circuit.probe_in_flight:
        circuit.probe_in_flight = True
        return  # this call is the probe -- let it through

    if remaining <= 0:
        # Cooldown elapsed but another call is already probing -- still
        # fail fast rather than sending a second concurrent probe.
        remaining = 0.0
    raise GoogleCircuitOpenError(provider, max(remaining, 0.0))


def _record_success(provider: str) -> None:
    circuit = _circuit_for(provider)
    circuit.consecutive_failures = 0
    circuit.opened_at = None
    circuit.probe_in_flight = False
    record_google_circuit_state(provider, "closed")


def _record_failure(provider: str, settings) -> None:
    circuit = _circuit_for(provider)
    circuit.probe_in_flight = False
    circuit.consecutive_failures += 1
    if circuit.consecutive_failures >= settings.google_circuit_failure_threshold:
        circuit.opened_at = time.monotonic()
        record_google_circuit_state(provider, "open")
    else:
        record_google_circuit_state(provider, "closed")


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

    _check_circuit(provider, settings)
    try:
        return await _do_request(
            provider,
            method,
            url,
            headers=headers,
            params=params,
            json=json,
            data=data,
            timeout=timeout,
            max_attempts=max_attempts,
            settings=settings,
        )
    except httpx.HTTPError:
        # Only a real request failure counts toward the breaker's threshold
        # -- a ValueError from a caller misconfiguration (max_attempts <= 0)
        # is not a signal that Google is unavailable, so it isn't caught
        # here and doesn't affect circuit state.
        _record_failure(provider, settings)
        raise
    finally:
        # Always clears, regardless of success/failure/cancellation/a
        # misconfiguration ValueError -- a probe that never resolves cleanly
        # must not leave probe_in_flight stuck true forever, which would
        # permanently wedge the circuit half-open. Redundant with (and
        # harmless alongside) the reset _record_success/_record_failure
        # already do on the normal paths.
        _circuit_for(provider).probe_in_flight = False


async def _do_request(
    provider: str,
    method: str,
    url: str,
    *,
    headers: dict | None,
    params: dict | None,
    json: dict | None,
    data: dict | None,
    timeout: float,
    max_attempts: int,
    settings,
) -> httpx.Response:
    last_exc: httpx.HTTPError | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method, url, headers=headers, params=params, json=json, data=data
                )
                response.raise_for_status()
            record_google_request(provider, "ok")
            _record_success(provider)
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
