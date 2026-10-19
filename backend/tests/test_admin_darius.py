"""Admin -> DARIUS bridge: access control, error mapping, decision audit, secrecy."""
from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from admin.darius import operator_client
from auth.jwt import create_access_token
from auth.password import hash_password
from main import app
from models.log import LogEntry
from models.user import User, UserRole
from services.darius_client import DariusClient

OPERATOR_TOKEN = "operator-secret-token-0123456789"
TASK = {
    "id": "t-1",
    "objective": "pay invoice",
    "status": "PAUSED",
    "createdAt": "2026-10-19T10:00:00.000Z",
    "updatedAt": "2026-10-19T10:00:01.000Z",
}
PREFIX = "/api/admin/darius"


class Upstream:
    """Scriptable DARIUS stand-in behind httpx.MockTransport."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item


def jr(status: int, body, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers)


@pytest.fixture
def upstream_for():
    def install(*responses: httpx.Response | Exception, token: str = OPERATOR_TOKEN) -> Upstream:
        upstream = Upstream(*responses)

        async def no_sleep(_s: float) -> None:
            return None

        darius = DariusClient(
            "http://darius.test", token, transport=httpx.MockTransport(upstream), sleep=no_sleep,
            max_attempts=2, label="operator",
        )
        app.dependency_overrides[operator_client] = lambda: darius
        return upstream

    yield install
    app.dependency_overrides.pop(operator_client, None)


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _make_user(session_factory, email: str, role: UserRole) -> User:
    async with session_factory() as session:
        user = User(
            email=email, full_name=email, hashed_password=hash_password("supersecret1"),
            role=role, is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def admin_user(session_factory) -> User:
    return await _make_user(session_factory, "admin@darioos.test", UserRole.ADMIN)


@pytest.fixture
def admin_headers(admin_user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(admin_user.id))}"}


@pytest.fixture
async def user_headers(session_factory) -> dict[str, str]:
    user = await _make_user(session_factory, "user@darioos.test", UserRole.USER)
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


async def _audit(session_factory) -> list[LogEntry]:
    async with session_factory() as session:
        rows = await session.execute(select(LogEntry).where(LogEntry.source == "darius_decision"))
        return list(rows.scalars())


READ_ENDPOINTS = [("GET", "/status"), ("GET", "/tasks"), ("GET", "/tasks/t-1"), ("GET", "/tasks/t-1/result")]
WRITE_ENDPOINTS = [("POST", "/tasks/t-1/approve"), ("POST", "/tasks/t-1/reject"), ("POST", "/tasks/t-1/cancel")]


@pytest.mark.parametrize("method,path", READ_ENDPOINTS + WRITE_ENDPOINTS)
async def test_requires_authentication_and_never_reaches_darius(client, upstream_for, method, path):
    upstream = upstream_for(jr(200, {}))
    response = await client.request(method, PREFIX + path)
    assert response.status_code == 401
    assert upstream.requests == []


@pytest.mark.parametrize("method,path", READ_ENDPOINTS + WRITE_ENDPOINTS)
async def test_non_admin_is_forbidden_and_never_reaches_darius(client, upstream_for, user_headers, method, path):
    upstream = upstream_for(jr(200, {}))
    response = await client.request(method, PREFIX + path, headers=user_headers)
    assert response.status_code == 403
    assert upstream.requests == []


async def test_list_tasks_forwards_filters_and_pagination(client, upstream_for, admin_headers):
    upstream = upstream_for(jr(200, [TASK], {"X-Total-Count": "3", "X-Next-Offset": "1"}))
    response = await client.get(PREFIX + "/tasks?status=PAUSED&limit=1&offset=0", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3 and body["next_offset"] == 1 and body["items"][0]["id"] == "t-1"
    assert dict(upstream.requests[0].url.params) == {"status": "PAUSED", "limit": "1", "offset": "0"}
    assert upstream.requests[0].headers["authorization"] == f"Bearer {OPERATOR_TOKEN}"


@pytest.mark.parametrize("query", ["status=BOGUS", "limit=0", "limit=201", "offset=-1"])
async def test_list_tasks_rejects_invalid_query_before_calling_darius(client, upstream_for, admin_headers, query):
    upstream = upstream_for(jr(200, []))
    response = await client.get(f"{PREFIX}/tasks?{query}", headers=admin_headers)
    assert response.status_code == 422
    assert upstream.requests == []


async def test_get_task_and_result_pass_through_validated_models(client, upstream_for, admin_headers):
    upstream_for(jr(200, {"taskId": "t-1", "objective": "x", "status": "RUNNING", "currentState": "ACT",
                          "iterations": 2, "trace": [{"state": "ACT", "output": "ok"}], "secretInternal": "drop"}))
    response = await client.get(PREFIX + "/tasks/t-1", headers=admin_headers)
    assert response.status_code == 200
    assert "secretInternal" not in response.json()

    upstream_for(jr(200, {"id": "t-1", "status": "COMPLETED", "done": True, "result": "r", "updatedAt": "x"}))
    response = await client.get(PREFIX + "/tasks/t-1/result", headers=admin_headers)
    assert response.json()["result"] == "r"


async def test_unavailable_darius_is_502_never_a_fake_success(client, upstream_for, admin_headers):
    upstream_for(httpx.ConnectError("refused"))
    response = await client.get(PREFIX + "/tasks", headers=admin_headers)
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "DARIUS_UNAVAILABLE"
    assert response.json()["detail"]["outcome_unknown"] is False


async def test_invalid_upstream_body_is_502(client, upstream_for, admin_headers):
    upstream_for(jr(200, {"nonsense": True}))
    response = await client.get(PREFIX + "/tasks/t-1/result", headers=admin_headers)
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "DARIUS_INVALID_RESPONSE"


async def test_rejected_credential_is_a_502_not_a_401_for_the_browser_user(client, upstream_for, admin_headers):
    upstream_for(jr(401, {"error": "Unauthorized"}))
    response = await client.get(PREFIX + "/tasks", headers=admin_headers)
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "DARIUS_CREDENTIAL_REJECTED"


async def test_not_found_is_404(client, upstream_for, admin_headers):
    upstream_for(jr(404, {"error": "Not found"}))
    assert (await client.get(PREFIX + "/tasks/t-1", headers=admin_headers)).status_code == 404
    # a path-like id never leaves the process
    upstream = upstream_for(jr(200, {}))
    assert (await client.get(PREFIX + "/tasks/a.b/result", headers=admin_headers)).status_code == 404
    assert upstream.requests == []


async def test_status_reports_not_configured_explicitly(client, admin_headers, monkeypatch):
    app.dependency_overrides[operator_client] = lambda: DariusClient("", "")
    try:
        response = await client.get(PREFIX + "/status", headers=admin_headers)
    finally:
        app.dependency_overrides.pop(operator_client, None)
    body = response.json()
    assert response.status_code == 200
    assert body["configured"] is False and body["reachable"] is False
    assert body["error"] == "DARIUS_NOT_CONFIGURED"


async def test_status_reports_reachable_with_latency_and_no_secrets(client, upstream_for, admin_headers):
    upstream_for(jr(200, {"status": "UNKNOWN"}))
    response = await client.get(PREFIX + "/status", headers=admin_headers)
    body = response.json()
    assert body["reachable"] is True and body["latency_ms"] is not None and body["circuit"] == "closed"
    assert OPERATOR_TOKEN not in response.text


async def test_status_reports_unreachable_explicitly(client, upstream_for, admin_headers):
    upstream_for(httpx.ConnectError("refused"))
    body = (await client.get(PREFIX + "/status", headers=admin_headers)).json()
    assert body["configured"] is True and body["reachable"] is False and body["latency_ms"] is None
    assert body["error"]


@pytest.mark.parametrize("action,decision,final", [("approve", "APPROVED", "RUNNING"), ("cancel", None, "CANCELLED")])
async def test_decision_is_relayed_once_and_audited_with_the_admin_user(
    client, upstream_for, admin_headers, admin_user, session_factory, action, decision, final
):
    ack = {"id": "t-1", "status": final, **({"decision": decision} if decision else {})}
    upstream = upstream_for(jr(200, ack))
    response = await client.post(f"{PREFIX}/tasks/t-1/{action}", headers=admin_headers)
    assert response.status_code == 200 and response.json()["status"] == final
    assert len(upstream.requests) == 1
    rows = await _audit(session_factory)
    assert len(rows) == 1
    assert rows[0].level == "info"
    assert rows[0].payload["action"] == action
    assert rows[0].payload["admin_user_id"] == admin_user.id
    assert rows[0].payload["outcome"] == "ok"
    assert OPERATOR_TOKEN not in json.dumps(rows[0].payload)


async def test_reject_forwards_the_reason_and_audits_it(client, upstream_for, admin_headers, session_factory):
    upstream = upstream_for(jr(200, {"id": "t-1", "status": "FAILED", "decision": "REJECTED"}))
    response = await client.post(
        PREFIX + "/tasks/t-1/reject", headers=admin_headers, json={"reason": "valor incorreto"}
    )
    assert response.status_code == 200
    assert json.loads(upstream.requests[0].content) == {"reason": "valor incorreto"}
    assert (await _audit(session_factory))[0].payload["reason"] == "valor incorreto"


async def test_reject_without_body_and_oversized_reason(client, upstream_for, admin_headers):
    upstream = upstream_for(jr(200, {"id": "t-1", "status": "FAILED", "decision": "REJECTED"}))
    assert (await client.post(PREFIX + "/tasks/t-1/reject", headers=admin_headers, json={})).status_code == 200
    too_long = await client.post(PREFIX + "/tasks/t-1/reject", headers=admin_headers, json={"reason": "x" * 501})
    assert too_long.status_code == 422
    assert len(upstream.requests) == 1


async def test_conflict_is_409_with_current_status_and_is_audited_as_error(
    client, upstream_for, admin_headers, session_factory
):
    body = {"error": "Task is not awaiting approval", "code": "NOT_AWAITING_APPROVAL", "status": "COMPLETED"}
    upstream = upstream_for(jr(409, body))
    response = await client.post(PREFIX + "/tasks/t-1/approve", headers=admin_headers)
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "NOT_AWAITING_APPROVAL" and detail["status"] == "COMPLETED"
    assert len(upstream.requests) == 1
    row = (await _audit(session_factory))[0]
    assert row.level == "warning" and row.payload["outcome"] == "error"
    assert row.payload["code"] == "NOT_AWAITING_APPROVAL"


async def test_lost_decision_reply_is_502_with_unknown_outcome_and_is_not_retried(
    client, upstream_for, admin_headers, session_factory
):
    upstream = upstream_for(httpx.ReadTimeout("slow"))
    response = await client.post(PREFIX + "/tasks/t-1/approve", headers=admin_headers)
    assert response.status_code == 502
    assert response.json()["detail"]["outcome_unknown"] is True
    assert len(upstream.requests) == 1  # max_attempts=2 on the client, yet a decision is sent once
    row = (await _audit(session_factory))[0]
    assert row.payload["outcome_unknown"] is True


async def test_decision_when_not_configured_is_503_and_nothing_is_sent(client, admin_headers, session_factory):
    app.dependency_overrides[operator_client] = lambda: DariusClient("", "")
    try:
        response = await client.post(PREFIX + "/tasks/t-1/approve", headers=admin_headers)
    finally:
        app.dependency_overrides.pop(operator_client, None)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DARIUS_NOT_CONFIGURED"
