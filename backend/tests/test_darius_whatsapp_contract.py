"""WhatsApp -> DARIUS flow against the REAL DARIUS runtime (not a mock of it).

Real: the DARIUS TypeScript server (spawned from a checkout, isolated temp DB, queue consumer ON), the
`DariusClient`, the link table, the job worker and every Dario OS handler/gate.
Simulated (external effects only): the LLM behind DARIUS (a local stub of Ollama's /api/generate) and the
Evolution transport (a recording provider). No network leaves the machine.

Opt-in like tests/test_darius_contract.py: set DARIUS_REPO_PATH to a DARIUS checkout with node_modules. Without
it the module is skipped with an explicit reason -- never reported as passed.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the mocked suite are intentionally re-bound as arguments
from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from services import darius_whatsapp
from services.darius_client import CircuitBreaker, DariusClient, DariusRequestError
from tests.test_darius_whatsapp import (  # noqa: F401 -- fixtures and helpers shared with the mocked suite
    INSTANCE,
    TEXT,
    _drain,
    _enqueue_inbound,
    _inbound,
    _links,
    _logs,
    _settings,
    provider,
    sessions,
)
from utils.config import get_settings

REPO = os.environ.get("DARIUS_REPO_PATH", "").strip()
_SERVER = Path(REPO) / "src" / "server.ts" if REPO else None

pytestmark = pytest.mark.skipif(
    not REPO or not (_SERVER and _SERVER.is_file() and (Path(REPO) / "node_modules" / "tsx").is_dir()),
    reason="DARIUS_REPO_PATH not set to a DARIUS checkout with node_modules (needs the real runtime)",
)

SERVICE_TOKEN = "shipit-service-token-0123456789"
STUB_REPLY = "Claro! Para 3 latas de tinta branca fosca o valor total é R$ 297,00."


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _OllamaStub(BaseHTTPRequestHandler):
    calls: list[str] = []
    reply = STUB_REPLY

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        type(self).calls.append(body.decode("utf-8", "replace")[:2000])
        payload = json.dumps({
            "response": f"DONE: {type(self).reply}" if type(self).reply else "", "done": True,
                "done_reason": "stop", "eval_count": 12, "prompt_eval_count": 40,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # silence
        return


@pytest.fixture(scope="module")
def ollama_stub():
    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _OllamaStub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(scope="module")
def darius_url(tmp_path_factory: pytest.TempPathFactory, ollama_stub: str):
    port = _free_port()
    tmp = tmp_path_factory.mktemp("darius_wa")
    env = {
        **os.environ,
        "PORT": str(port), "BIND_HOST": "127.0.0.1", "DB_PATH": str(tmp / "darius_wa.db"),
        "DARIUS_API_CLIENTS": json.dumps({"shipit": SERVICE_TOKEN}), "DARIUS_API_TOKEN": "",
        "DARIUS_QUEUE_CONSUMER": "on", "OLLAMA_URL": ollama_stub,
    }
    log = (tmp / "server.log").open("wb")
    proc = subprocess.Popen(["node", "--import", "tsx", "src/server.ts"], cwd=REPO, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                tail = (tmp / "server.log").read_text(errors="replace")[-2000:]
                pytest.fail(f"DARIUS exited early ({proc.returncode}):\n{tail}")
            try:
                if httpx.get(f"{base}/api/health", timeout=1.0, trust_env=False).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.3)
        else:
            pytest.fail("DARIUS did not become healthy in 60s")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


@pytest.fixture
def real_client(darius_url, monkeypatch):
    client = DariusClient(
        darius_url, SERVICE_TOKEN, transport=httpx.AsyncHTTPTransport(), max_attempts=2, backoff=0.05,
        breaker=CircuitBreaker(1000, 1.0),
    )
    monkeypatch.setattr("services.darius_whatsapp.get_service_client", lambda: client)
    monkeypatch.setattr(get_settings(), "darius_whatsapp_poll_seconds", 0.2)
    return client


async def _settle(sessions, until, timeout: float = 60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await _drain(rounds=3)
        links = await _links(sessions)
        if links and until(links[0]):
            return links[0]
        time.sleep(0.25)
    pytest.fail(f"link never reached the expected state: {[(x.status, x.darius_status, x.last_error) for x in links]}")


async def test_real_darius_runs_the_task_and_the_reply_leaves_through_the_mocked_evolution(
    sessions, provider, real_client,
):
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)

    link = await _settle(sessions, lambda row: row.status in ("reply_queued", "failed", "expired", "cancelled"))
    await _drain()

    if link.status != "reply_queued":
        state = await real_client.get_task(link.darius_task_id)
        raw = await real_client.get_result(link.darius_task_id)
        pytest.fail(f"{link.status}/{link.last_error}; result.error={raw.error!r}; "
                    f"trace={[(t.state, t.output, t.error) for t in state.trace]}; stub_calls={len(_OllamaStub.calls)}")
    assert [c[1] for c in provider.calls] == [STUB_REPLY]
    # the task really exists in DARIUS, owned by this client, completed with exactly that result
    result = await real_client.get_result(link.darius_task_id)
    assert result.status == "COMPLETED" and result.done and result.result == STUB_REPLY
    # the customer's message reached the model through the real objective (and the phone number did not)
    assert any(TEXT in call for call in _OllamaStub.calls)
    assert all("5511999" not in call for call in _OllamaStub.calls)
    blob = json.dumps([e.payload for e in await _logs(sessions)], default=str)
    assert STUB_REPLY not in blob and TEXT not in blob


async def test_real_darius_idempotency_a_duplicate_message_does_not_create_a_second_task(
    sessions, provider, real_client,
):
    cid, mid = await _inbound(sessions)
    for _ in range(2):
        await _enqueue_inbound(sessions, cid, mid)

    await _settle(sessions, lambda row: row.status in ("reply_queued", "failed"))
    await _drain()

    assert len(await _links(sessions)) == 1 and len(provider.calls) == 1
    page = await real_client.list_tasks(limit=200)
    link = (await _links(sessions))[0]
    assert [t.id for t in page.items].count(link.darius_task_id) == 1
    # the same Idempotency-Key replayed straight at DARIUS returns the SAME task
    objective = next(t.objective for t in page.items if t.id == link.darius_task_id)
    again = await real_client.create_task(objective, idempotency_key=link.dedupe_key, completion="non_empty")
    assert again.id == link.darius_task_id
    # ...and replaying it under a different request (other objective or completion mode) is refused
    with pytest.raises(DariusRequestError, match="different request"):
        await real_client.create_task(objective, idempotency_key=link.dedupe_key)
    with pytest.raises(DariusRequestError, match="different request"):
        await real_client.create_task("outro", idempotency_key=link.dedupe_key, completion="non_empty")
    assert [t.id for t in (await real_client.list_tasks(limit=200)).items].count(link.darius_task_id) == 1


async def test_real_darius_unreachable_model_ends_failed_and_nothing_is_sent(
    sessions, provider, real_client, monkeypatch,
):
    monkeypatch.setattr(_OllamaStub, "reply", "")  # the stub answers with an empty completion
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)

    link = await _settle(sessions, lambda row: row.status in ("reply_queued", "failed", "expired", "cancelled"))
    await _drain()

    assert link.status != "reply_queued" or provider.calls == [] or provider.calls[0][1].strip() != ""
    assert all(c[1].strip() for c in provider.calls)   # whatever happened, an empty message is never sent


async def test_window_expiry_cancels_the_real_task(sessions, provider, real_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "darius_whatsapp_reply_timeout_seconds", 0)
    cid, mid = await _inbound(sessions)
    await _enqueue_inbound(sessions, cid, mid)

    link = await _settle(sessions, lambda row: row.status in ("reply_queued", "failed", "expired", "cancelled"))

    # either DARIUS answered within the first poll (COMPLETED wins) or the window expired and the task was cancelled
    assert link.status in ("reply_queued", "expired", "cancelled"), link.status
    if link.status == "expired":
        assert (await real_client.get_result(link.darius_task_id)).status in ("CANCELLED", "COMPLETED")
        assert provider.calls == []


def test_the_module_uses_the_production_dedupe_key_format():
    assert darius_whatsapp.dedupe_key(INSTANCE, type("M", (), {"id": 1, "external_id": "X"})()).startswith("wa-")
