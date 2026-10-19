"""DARIUS adapter: contract, retry safety, circuit breaker, error mapping, secrecy.

These tests use httpx.MockTransport (no network). The same contract is exercised
against the REAL DARIUS server in test_darius_contract.py.
"""
from __future__ import annotations

import json

import httpx
import pytest

from services.darius_client import (
    CircuitBreaker,
    DariusAuthError,
    DariusClient,
    DariusConflict,
    DariusInvalidResponse,
    DariusNotConfigured,
    DariusNotFound,
    DariusRequestError,
    DariusUnavailable,
)

TOKEN = "super-secret-token-0123456789"
TASK = {
    "id": "t-1",
    "objective": "do it",
    "status": "RUNNING",
    "createdAt": "2026-10-19T10:00:00.000Z",
    "updatedAt": "2026-10-19T10:00:01.000Z",
}


class Recorder:
    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item


def make(rec: Recorder, **kw) -> DariusClient:
    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    client = DariusClient(
        "http://darius.test", TOKEN, transport=httpx.MockTransport(rec), sleep=fake_sleep, backoff=0.5, **kw
    )
    client.slept = slept  # type: ignore[attr-defined]
    return client


def jr(status: int, body, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers)


async def test_authenticates_with_bearer_and_never_exposes_the_token():
    rec = Recorder(jr(200, {"status": "UNKNOWN"}))
    client = make(rec)
    await client.health()
    assert rec.requests[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in repr(client)
    assert TOKEN not in str(client.__dict__.get("label", ""))


async def test_not_configured_never_calls_the_network():
    rec = Recorder(jr(200, {}))
    for base, token in (("", TOKEN), ("http://darius.test", "")):
        client = DariusClient(base, token, transport=httpx.MockTransport(rec))
        assert client.configured is False
        with pytest.raises(DariusNotConfigured):
            await client.list_tasks()
    assert rec.requests == []


async def test_get_is_retried_on_5xx_then_succeeds_with_exponential_backoff():
    ok = {"id": "t-1", "status": "COMPLETED", "done": True, "result": "r", "updatedAt": "x"}
    rec = Recorder(jr(503, {"error": "down"}), jr(502, {"error": "down"}), jr(200, ok))
    client = make(rec)
    result = await client.get_result("t-1")
    assert result.done is True and result.result == "r"
    assert len(rec.requests) == 3
    assert client.slept == [0.5, 1.0]  # type: ignore[attr-defined]


async def test_client_errors_are_not_retried_and_map_to_specific_exceptions():
    cases = [
        (401, DariusAuthError),
        (403, DariusAuthError),
        (404, DariusNotFound),
        (409, DariusConflict),
        (413, DariusRequestError),
        (422, DariusRequestError),
    ]
    for status, exc in cases:
        rec = Recorder(jr(status, {"error": "nope", "code": "X", "status": "COMPLETED"}))
        client = make(rec)
        with pytest.raises(exc) as info:
            await client.get_result("t-1")
        assert len(rec.requests) == 1, status
        assert info.value.status_code == status
        assert info.value.code == "X"


async def test_conflict_carries_the_current_task_status():
    body = {"error": "Task is not awaiting approval", "code": "NOT_AWAITING_APPROVAL", "status": "COMPLETED"}
    rec = Recorder(jr(409, body))
    with pytest.raises(DariusConflict) as info:
        await make(rec).approve("t-1")
    assert info.value.code == "NOT_AWAITING_APPROVAL"
    assert info.value.task_status == "COMPLETED"


async def test_decisions_are_sent_once_and_flag_an_unknown_outcome_on_failure():
    for action in ("approve", "cancel"):
        rec = Recorder(jr(503, {"error": "down"}))
        client = make(rec)
        with pytest.raises(DariusUnavailable) as info:
            await getattr(client, action)("t-1")
        assert len(rec.requests) == 1  # never repeated
        assert info.value.outcome_unknown is True

    rec = Recorder(httpx.ReadTimeout("slow"))
    client = make(rec)
    with pytest.raises(DariusUnavailable) as info:
        await client.reject("t-1", "no")
    assert len(rec.requests) == 1
    assert info.value.outcome_unknown is True
    assert json.loads(rec.requests[0].content) == {"reason": "no"}


async def test_reads_never_report_an_unknown_outcome():
    rec = Recorder(httpx.ConnectError("refused"))
    client = make(rec)
    with pytest.raises(DariusUnavailable) as info:
        await client.get_result("t-1")
    assert info.value.outcome_unknown is False
    assert len(rec.requests) == 3  # retried up to max_attempts


async def test_create_task_requires_an_idempotency_key_and_replays_the_same_key_on_retry():
    client = make(Recorder(jr(200, TASK)))
    with pytest.raises(ValueError):
        await client.create_task("x", idempotency_key="  ")

    rec = Recorder(httpx.ConnectError("refused"), jr(200, TASK))
    client = make(rec)
    task = await client.create_task("do it", idempotency_key="wa:inst:msg-1", model_name="m")
    assert task.id == "t-1"
    assert [r.headers["idempotency-key"] for r in rec.requests] == ["wa:inst:msg-1", "wa:inst:msg-1"]
    assert json.loads(rec.requests[1].content) == {"objective": "do it", "modelName": "m"}


async def test_list_tasks_parses_the_page_headers_and_validates_arguments():
    rec = Recorder(jr(200, [TASK], {"X-Total-Count": "7", "X-Next-Offset": "1"}))
    client = make(rec)
    page = await client.list_tasks(status="RUNNING", limit=1, offset=0)
    assert (page.total, page.next_offset, page.items[0].id) == (7, 1, "t-1")
    assert dict(rec.requests[0].url.params) == {"limit": "1", "offset": "0", "status": "RUNNING"}
    for kwargs in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
        with pytest.raises(ValueError):
            await client.list_tasks(**kwargs)


async def test_invalid_responses_are_reported_never_guessed():
    bad_pages = [
        jr(200, [TASK]),  # missing X-Total-Count
        jr(200, {"not": "a list"}, {"X-Total-Count": "1"}),
        jr(200, [{"id": "t-1"}], {"X-Total-Count": "1"}),  # missing required fields
        jr(200, [TASK | {"status": "WEIRD"}], {"X-Total-Count": "1"}),  # unknown status
        httpx.Response(200, content=b"<html>proxy page</html>", headers={"X-Total-Count": "1"}),
    ]
    for resp in bad_pages:
        with pytest.raises(DariusInvalidResponse):
            await make(Recorder(resp)).list_tasks()
    with pytest.raises(DariusInvalidResponse):
        await make(Recorder(jr(200, {"id": "t-1"}))).get_result("t-1")
    with pytest.raises(DariusInvalidResponse):
        await make(Recorder(jr(200, {"taskId": "t-1"}))).get_task("t-1")
    # a 200 with a malformed decision body: the decision may have been applied
    with pytest.raises(DariusInvalidResponse) as info:
        await make(Recorder(jr(200, {"unexpected": True}))).approve("t-1")
    assert info.value.outcome_unknown is True


async def test_extra_fields_from_a_newer_runtime_are_tolerated():
    rec = Recorder(jr(200, [TASK | {"newField": 1}], {"X-Total-Count": "1"}))
    assert (await make(rec).list_tasks()).items[0].id == "t-1"


async def test_task_ids_that_could_traverse_paths_never_leave_the_process():
    rec = Recorder(jr(200, {}))
    client = make(rec)
    for bad in ("../admin", "a/b", "a.b", "", "x" * 129, "a b"):
        with pytest.raises(DariusNotFound):
            await client.get_result(bad)
    assert rec.requests == []


async def test_rate_limit_is_retried_for_reads_and_exposes_retry_after():
    rec = Recorder(jr(429, {"error": "slow down", "code": "RATE_LIMIT"}, {"Retry-After": "2"}))
    client = make(rec)
    with pytest.raises(DariusRequestError) as info:
        await client.get_result("t-1")
    assert info.value.retry_after == 2.0
    assert info.value.code == "RATE_LIMIT"
    assert len(rec.requests) == 3
    assert client.slept == [2.0, 2.0]  # type: ignore[attr-defined]


async def test_error_messages_never_echo_the_raw_body():
    rec = Recorder(httpx.Response(500, content=b"stack trace with " + TOKEN.encode()))
    with pytest.raises(DariusUnavailable) as info:
        await make(rec).approve("t-1")
    assert TOKEN not in str(info.value)
    assert "stack trace" not in str(info.value)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_circuit_opens_after_consecutive_failures_fails_fast_and_recovers():
    clock = FakeClock()
    rec = Recorder(jr(503, {"error": "down"}))
    client = make(rec, breaker=CircuitBreaker(3, 30.0, clock))
    client._max_attempts = 1  # one call per request keeps the count explicit

    for _ in range(3):
        with pytest.raises(DariusUnavailable):
            await client.get_result("t-1")
    assert client.breaker.state == "open"

    calls_before = len(rec.requests)
    with pytest.raises(DariusUnavailable) as info:
        await client.get_result("t-1")
    assert info.value.code == "CIRCUIT_OPEN"
    assert len(rec.requests) == calls_before  # failed fast: no network call

    clock.now += 31  # cooldown elapsed -> half open: one probe is allowed
    assert client.breaker.state == "half_open"
    with pytest.raises(DariusUnavailable):
        await client.get_result("t-1")  # probe fails -> open again
    assert client.breaker.state == "open"

    clock.now += 31
    rec.responses[:] = [jr(200, {"id": "t-1", "status": "RUNNING", "done": False, "updatedAt": "x"})]
    await client.get_result("t-1")  # probe succeeds -> closed
    assert client.breaker.state == "closed"
    assert client.breaker.consecutive_failures == 0


async def test_client_errors_do_not_count_against_the_circuit():
    rec = Recorder(jr(404, {"error": "Not found"}))
    client = make(rec, breaker=CircuitBreaker(2, 30.0))
    for _ in range(5):
        with pytest.raises(DariusNotFound):
            await client.get_result("t-1")
    assert client.breaker.state == "closed"
