"""Review fix (priority 3): send_whatsapp_text's commit-before-transport
fence (jobs/handlers.py, review finding A) only protects against the JOB
WORKER blindly re-running a whole job after a crash. It does nothing
about THIS layer -- providers/whatsapp/base.py's `_request` -- retrying
the HTTP call again INSIDE the same job execution after the provider
accepted the message but the response timed out. That could still send
the same WhatsApp message twice, with no crash or worker retry involved
at all.

Tested here against a REAL httpx.AsyncClient call path (not a mock of
_request itself) with a deterministic fake transport standing in for the
network -- proving:

  1. A response timeout on a send (EvolutionProvider._post, used by every
     send_* method) results in exactly ONE POST attempt, not a blind retry.
  2. This is NOT a blanket "sends never retry" rule: a ConnectError (the
     request never left this process, no delivery ambiguity at all)
     still retries normally through the same send path.
  3. The `retry_on_ambiguous_delivery` flag genuinely controls the
     behavior -- a caller that opts back into retrying (as some future
     read-only/idempotent call might) still retries on timeout too.

Review fix (second round): the first version of this protection only
named ReadTimeout/WriteTimeout as "ambiguous". That missed ReadError,
WriteError (a connection reset mid-request/response -- the request may
have already reached the provider) and RemoteProtocolError (the server
closed the connection or spoke invalid HTTP after the exchange started).
base.py now uses an ALLOW-list of proven-safe-to-retry errors instead
(ConnectError/ConnectTimeout/PoolTimeout -- failures before any request
byte could have reached the provider) so these additional cases are
covered without having to enumerate every ambiguous exception type by
name. Covered below: ReadError, WriteError, RemoteProtocolError each
do NOT retry when sending; ConnectTimeout and PoolTimeout (the other two
allow-listed, pre-send failures) still DO retry, same as ConnectError.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

from conftest import load_real_module

HERE = Path(__file__).parent
BACKEND_ROOT = HERE.parents[0]
APP_STUB = str(HERE / "app_stub")
if APP_STUB not in sys.path:
    sys.path.insert(0, APP_STUB)

_REAL_MODULE_KEYS = ("providers.whatsapp.base", "providers.whatsapp.evolution.provider")


@pytest.fixture(scope="module", autouse=True)
def _real_modules():
    saved = {key: sys.modules.get(key) for key in _REAL_MODULE_KEYS}
    try:
        load_real_module("providers.whatsapp.base", BACKEND_ROOT / "providers" / "whatsapp" / "base.py")
        load_real_module(
            "providers.whatsapp.evolution.provider",
            BACKEND_ROOT / "providers" / "whatsapp" / "evolution" / "provider.py",
        )
        yield
    finally:
        for key, mod in saved.items():
            if mod is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = mod


@pytest.fixture
def base_module(_real_modules):
    return sys.modules["providers.whatsapp.base"]


@pytest.fixture
def evolution_provider_class(_real_modules):
    return sys.modules["providers.whatsapp.evolution.provider"].EvolutionProvider


class _CountingAsyncClient:
    """Deterministic stand-in for httpx.AsyncClient -- no real network,
    no real timing, just a scripted sequence of outcomes and an exact
    call count every assertion below checks."""

    outcomes: list[object] = []
    calls: int = 0

    def __init__(self, *, timeout=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def request(self, method, url, json=None, headers=None):
        type(self).calls += 1
        outcome = type(self).outcomes[min(type(self).calls - 1, len(type(self).outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def fake_transport(base_module):
    original = base_module.httpx.AsyncClient
    base_module.httpx.AsyncClient = _CountingAsyncClient
    _CountingAsyncClient.calls = 0
    _CountingAsyncClient.outcomes = []
    try:
        yield _CountingAsyncClient
    finally:
        base_module.httpx.AsyncClient = original


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}
        self._json_body = json_body or {"key": {"id": "EVT-OK"}}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://example.invalid")
            raise httpx.HTTPStatusError("bad status", request=request, response=self)

    def json(self):
        return self._json_body


def _settings_for(base_module, *, max_attempts, backoff_seconds=0.0):
    from utils.config import get_settings

    settings = get_settings()
    saved = {
        "whatsapp_request_max_attempts": getattr(settings, "whatsapp_request_max_attempts", None),
        "whatsapp_request_backoff_seconds": getattr(settings, "whatsapp_request_backoff_seconds", None),
    }
    settings.whatsapp_request_max_attempts = max_attempts
    settings.whatsapp_request_backoff_seconds = backoff_seconds
    return settings, saved


def _restore_settings(settings, saved):
    for key, value in saved.items():
        setattr(settings, key, value)


@pytest.mark.asyncio
async def test_send_through_evolution_provider_does_not_retry_on_read_timeout(
    evolution_provider_class, fake_transport,
):
    """The exact scenario the review described: the provider may have
    already accepted/processed the message, and the response never came
    back. Must attempt the POST exactly once -- not resend it."""
    settings, saved = _settings_for(sys.modules["providers.whatsapp.base"], max_attempts=3)
    settings.evolution_base_url = "http://example.invalid"
    settings.evolution_api_key = ""
    settings.evolution_instance = "dario"
    fake_transport.outcomes = [httpx.ReadTimeout("simulated: response never arrived")]
    try:
        provider = evolution_provider_class()
        with pytest.raises(Exception):
            await provider.send_text("+5511999990000", "mensagem de teste")
        assert fake_transport.calls == 1, "retentou o POST apos um timeout de resposta -- risco de enviar a mensagem duas vezes"
    finally:
        _restore_settings(settings, saved)


@pytest.mark.asyncio
async def test_send_through_evolution_provider_still_retries_on_connect_error(
    evolution_provider_class, fake_transport,
):
    """Not a blanket "sends never retry": a ConnectError means the
    request never reached the provider at all -- no delivery ambiguity --
    so the normal retry-with-backoff policy still applies."""
    settings, saved = _settings_for(sys.modules["providers.whatsapp.base"], max_attempts=3)
    settings.evolution_base_url = "http://example.invalid"
    settings.evolution_api_key = ""
    settings.evolution_instance = "dario"
    fake_transport.outcomes = [
        httpx.ConnectError("simulated: connection refused"),
        httpx.ConnectError("simulated: connection refused"),
        _FakeResponse(200),
    ]
    try:
        provider = evolution_provider_class()
        result = await provider.send_text("+5511999990000", "mensagem de teste")
        assert result == {"key": {"id": "EVT-OK"}}
        assert fake_transport.calls == 3, "nao tentou de novo apos ConnectError -- isso nao deveria ter sido bloqueado"
    finally:
        _restore_settings(settings, saved)


@pytest.mark.asyncio
async def test_retry_on_ambiguous_delivery_flag_genuinely_controls_the_behavior(
    base_module, fake_transport,
):
    """Calling _request directly with retry_on_ambiguous_delivery=True (the
    default, for any future read-only/idempotent caller) must still retry
    on a read timeout -- proving the no-retry behavior above comes from
    the flag _post sets, not a hardcoded blanket rule inside _request."""
    settings, saved = _settings_for(base_module, max_attempts=3)
    fake_transport.outcomes = [
        httpx.ReadTimeout("simulated"),
        httpx.ReadTimeout("simulated"),
        _FakeResponse(200),
    ]
    try:
        class _Probe(base_module.WhatsAppProvider):
            name = "probe"

            async def send_text(self, to, content, **kw): ...
            async def send_image(self, to, url, **kw): ...
            async def send_file(self, to, url, **kw): ...
            async def send_audio(self, to, url, **kw): ...
            async def send_location(self, to, lat, lng, **kw): ...
            def parse_webhook(self, payload): ...

        probe = _Probe()
        result = await probe._request(
            "GET", "http://example.invalid/status", retry_on_ambiguous_delivery=True,
        )
        assert result == {"key": {"id": "EVT-OK"}}
        assert fake_transport.calls == 3
    finally:
        _restore_settings(settings, saved)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda: httpx.ReadError("simulated: connection reset while reading the response"),
        lambda: httpx.WriteError("simulated: connection reset while writing the request"),
        lambda: httpx.RemoteProtocolError("simulated: server closed the connection mid-response"),
    ],
    ids=["ReadError", "WriteError", "RemoteProtocolError"],
)
async def test_send_does_not_retry_on_other_ambiguous_transport_errors(
    evolution_provider_class, fake_transport, exc_factory,
):
    """Review regression (round 4): the first version of this protection
    only recognized ReadTimeout/WriteTimeout as ambiguous. ReadError,
    WriteError and RemoteProtocolError are just as ambiguous -- the
    request may already have reached the provider -- and a blind retry
    on any of them risks exactly the same double-send."""
    settings, saved = _settings_for(sys.modules["providers.whatsapp.base"], max_attempts=3)
    settings.evolution_base_url = "http://example.invalid"
    settings.evolution_api_key = ""
    settings.evolution_instance = "dario"
    fake_transport.outcomes = [exc_factory()]
    try:
        provider = evolution_provider_class()
        with pytest.raises(Exception):
            await provider.send_text("+5511999990000", "mensagem de teste")
        assert fake_transport.calls == 1, "retentou o POST apos um erro ambiguo de transporte -- risco de enviar a mensagem duas vezes"
    finally:
        _restore_settings(settings, saved)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda: httpx.ConnectTimeout("simulated: could not establish the connection in time"),
        lambda: httpx.PoolTimeout("simulated: no free connection became available in time"),
    ],
    ids=["ConnectTimeout", "PoolTimeout"],
)
async def test_send_still_retries_on_other_safe_to_retry_transport_errors(
    evolution_provider_class, fake_transport, exc_factory,
):
    """The allow-list covers more than ConnectError: ConnectTimeout and
    PoolTimeout are also failures that happen before any request byte
    could have reached the provider, so they keep retrying normally."""
    settings, saved = _settings_for(sys.modules["providers.whatsapp.base"], max_attempts=3)
    settings.evolution_base_url = "http://example.invalid"
    settings.evolution_api_key = ""
    settings.evolution_instance = "dario"
    fake_transport.outcomes = [exc_factory(), exc_factory(), _FakeResponse(200)]
    try:
        provider = evolution_provider_class()
        result = await provider.send_text("+5511999990000", "mensagem de teste")
        assert result == {"key": {"id": "EVT-OK"}}
        assert fake_transport.calls == 3, "nao tentou de novo apos um erro seguro de transporte -- isso nao deveria ter sido bloqueado"
    finally:
        _restore_settings(settings, saved)


@pytest.mark.asyncio
@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [500, 502, 504], ids=["500", "502", "504"])
async def test_send_does_not_retry_on_an_http_error_status_even_though_a_response_was_received(
    evolution_provider_class, fake_transport, status_code,
):
    """Review finding (round 6): the previous version of this protection
    excluded HTTPStatusError from "ambiguous" entirely, on the theory that
    receiving a response (even an error one) proves the provider told us
    definitively what happened. That theory is wrong: a gateway can
    accept and queue a WhatsApp send, then fail composing or delivering
    its OWN response -- 500/502/504 included -- well after the message
    was already in flight. max_attempts=3 here (not 1) is what proves
    this: if the old exclusion were still in place, this would retry up
    to 3 times like any ordinary transient failure; it must now stop
    after exactly one attempt, the same as a ReadTimeout."""
    settings, saved = _settings_for(sys.modules["providers.whatsapp.base"], max_attempts=3)
    settings.evolution_base_url = "http://example.invalid"
    settings.evolution_api_key = ""
    settings.evolution_instance = "dario"
    fake_transport.outcomes = [_FakeResponse(status_code)]
    try:
        provider = evolution_provider_class()
        with pytest.raises(Exception):
            await provider.send_text("+5511999990000", "mensagem de teste")
        assert fake_transport.calls == 1, (
            f"retentou o POST apos um {status_code} -- a mensagem pode ja ter sido aceita pelo provedor"
        )
    finally:
        _restore_settings(settings, saved)


@pytest.mark.asyncio
async def test_a_confirmed_send_still_continues_normally_on_the_next_turn(
    evolution_provider_class, fake_transport,
):
    """Control case: once a send genuinely succeeds (a real 200 with a
    recognized receipt shape), the next, unrelated send on the same
    conversation must behave exactly like an ordinary, unaffected call --
    proving the ambiguous-outcome protection is scoped to the failing
    attempt, not a lingering state that taints the conversation."""
    settings, saved = _settings_for(sys.modules["providers.whatsapp.base"], max_attempts=3)
    settings.evolution_base_url = "http://example.invalid"
    settings.evolution_api_key = ""
    settings.evolution_instance = "dario"
    try:
        provider = evolution_provider_class()

        fake_transport.outcomes = [_FakeResponse(200, {"key": {"id": "EVT-FIRST"}})]
        first = await provider.send_text("+5511999990000", "primeira mensagem")
        assert first == {"key": {"id": "EVT-FIRST"}}
        assert fake_transport.calls == 1

        fake_transport.calls = 0
        fake_transport.outcomes = [_FakeResponse(200, {"key": {"id": "EVT-SECOND"}})]
        second = await provider.send_text("+5511999990000", "segunda mensagem, turno seguinte")
        assert second == {"key": {"id": "EVT-SECOND"}}
        assert fake_transport.calls == 1
    finally:
        _restore_settings(settings, saved)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
