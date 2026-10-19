"""Contract test: the adapter against the REAL DARIUS server (not a mock).

Spawns `src/server.ts` of a DARIUS checkout on a free loopback port with an
isolated temp database and three credentials (two regular clients + one admin
operator), then verifies authentication, owner isolation, pagination,
idempotent creation and the admin-only decision rules end to end.

Opt-in: set DARIUS_REPO_PATH to a DARIUS OSS checkout with installed
dependencies. Without it the module is skipped with an explicit reason --
it is never reported as passed.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from services.darius_client import (
    DariusAuthError,
    DariusClient,
    DariusConflict,
    DariusNotFound,
)

REPO = os.environ.get("DARIUS_REPO_PATH", "").strip()
_SERVER = Path(REPO) / "src" / "server.ts" if REPO else None

pytestmark = pytest.mark.skipif(
    not REPO or not (_SERVER and _SERVER.is_file() and (Path(REPO) / "node_modules" / "tsx").is_dir()),
    reason="DARIUS_REPO_PATH not set to a DARIUS checkout with node_modules (contract test needs the real runtime)",
)

TOKENS = {
    "shipit": "shipit-service-token-0123456789",
    "other": "other-client-token-0123456789ab",
    "ops": "ops-operator-token-0123456789cd",
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def darius_url(tmp_path_factory: pytest.TempPathFactory):
    port = _free_port()
    tmp = tmp_path_factory.mktemp("darius")
    env = {
        **os.environ,
        "PORT": str(port),
        "BIND_HOST": "127.0.0.1",
        "DB_PATH": str(tmp / "darius_contract.db"),
        "DARIUS_API_CLIENTS": json.dumps(
            {"shipit": TOKENS["shipit"], "other": TOKENS["other"], "ops": {"token": TOKENS["ops"], "admin": True}}
        ),
        "DARIUS_API_TOKEN": "",
        "DARIUS_QUEUE_CONSUMER": "off",
        "OLLAMA_URL": "http://127.0.0.1:9",  # unreachable by design: tasks fail, nothing leaves the machine
    }
    log = (tmp / "server.log").open("wb")
    proc = subprocess.Popen(
        ["node", "--import", "tsx", "src/server.ts"], cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT
    )
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


def _client(base: str, who: str, token: str | None = None) -> DariusClient:
    return DariusClient(
        base, token or TOKENS[who], transport=httpx.AsyncHTTPTransport(), max_attempts=2, backoff=0.05, label=who
    )


async def test_health_is_open_and_reports_unknown_not_a_fake_ok(darius_url):
    body = await _client(darius_url, "shipit").health()
    assert body.get("status") == "UNKNOWN"


async def test_invalid_token_is_rejected(darius_url):
    with pytest.raises(DariusAuthError) as info:
        await _client(darius_url, "shipit", token="not-a-valid-token-0000000000").list_tasks()
    assert info.value.status_code == 401


async def test_owner_isolation_and_operator_visibility(darius_url):
    service, other, ops = (_client(darius_url, w) for w in ("shipit", "other", "ops"))
    task = await service.create_task("contract: isolation", idempotency_key="contract-iso-1")

    assert task.id in {t.id for t in (await service.list_tasks()).items}
    assert task.id not in {t.id for t in (await other.list_tasks()).items}
    with pytest.raises(DariusNotFound):
        await other.get_result(task.id)  # uniform 404: existence is not disclosed
    with pytest.raises(DariusNotFound):
        await other.cancel(task.id)

    assert task.id in {t.id for t in (await ops.list_tasks()).items}
    assert (await ops.get_result(task.id)).id == task.id


async def test_create_is_idempotent_for_the_same_key(darius_url):
    service = _client(darius_url, "shipit")
    first = await service.create_task("contract: idem", idempotency_key="contract-idem-1")
    again = await service.create_task("contract: idem", idempotency_key="contract-idem-1")
    assert again.id == first.id


async def test_pagination_headers_match_the_adapter_contract(darius_url):
    service = _client(darius_url, "shipit")
    for i in range(3):
        await service.create_task(f"contract: page {i}", idempotency_key=f"contract-page-{i}")
    page = await service.list_tasks(limit=2, offset=0)
    assert len(page.items) == 2 and page.total >= 3 and page.next_offset == 2
    last = await service.list_tasks(limit=2, offset=page.total - 1)
    assert len(last.items) == 1 and last.next_offset is None


async def test_decisions_are_admin_only_and_conflicts_are_typed(darius_url):
    service, ops = _client(darius_url, "shipit"), _client(darius_url, "ops")
    task = await service.create_task("contract: decisions", idempotency_key="contract-dec-1")

    # an automated (non-admin) client can never approve or reject its own task
    for call in (service.approve(task.id), service.reject(task.id, "no")):
        with pytest.raises(DariusAuthError) as info:
            await call
        assert info.value.status_code == 403

    # the admin credential is allowed, but the task is not awaiting approval -> typed 409
    with pytest.raises(DariusConflict) as conflict:
        await ops.approve(task.id)
    assert conflict.value.code == "NOT_AWAITING_APPROVAL"
    assert conflict.value.task_status is not None


async def test_cancel_by_owner_has_one_of_the_two_documented_outcomes(darius_url):
    service = _client(darius_url, "shipit")
    task = await service.create_task("contract: cancel", idempotency_key="contract-cancel-1")
    try:
        ack = await service.cancel(task.id)
        assert ack.status == "CANCELLED"
    except DariusConflict as exc:
        # with no reachable model the task may already be terminal
        assert exc.code == "ALREADY_FINISHED"
