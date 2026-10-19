"""Admin -> DARIUS bridge, operations views: runtime metrics relay, failure class on results, and the list of
conversations a human took over (the only place where this panel can tell why DARIUS stays silent)."""
# ruff: noqa: F811  -- pytest fixtures imported from the bridge suite are re-declared as test parameters
from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import text

from models.contact import Contact
from services import conversation_control
from tests.test_admin_darius import (  # noqa: F401 -- fixtures and helpers shared with the bridge suite
    PREFIX,
    admin_headers,
    admin_user,
    jr,
    session_factory,
    upstream_for,
    user_headers,
)
from tests.test_darius_whatsapp import _migrate_control_tables_sync

METRICS = {
    "generatedAt": 1760900000000,
    "scope": {"durable": "store", "process": "restarts with the process"},
    "tasks": {"available": True, "total": 7, "byStatus": {"PENDING": 0, "QUEUED": 2, "RUNNING": 1, "PAUSED": 1,
                                                          "COMPLETED": 2, "FAILED": 1, "CANCELLED": 0}},
    "queue": {"queued": 2, "backingOff": 1, "nextRetryAt": 1760900005000},
    "engine": {"workerId": "w1", "since": 1760899000000, "activeLoops": 1,
               "consumer": {"running": True, "concurrency": 2, "inflight": 1, "passes": 40, "startedTotal": 3,
                            "lastPassAt": 1760899999000},
               "recovery": {"running": True, "sweeps": 9, "requeuedTotal": 0, "failedTotal": 0, "lastSweepAt": None},
               "retry": {"enabled": True, "maxRetries": 3, "scheduledTotal": 2, "exhaustedTotal": 0}},
    "scheduler": {"enabled": False},
}


async def test_metrics_requires_admin_and_is_relayed_verbatim(client, upstream_for, admin_headers, user_headers):
    upstream = upstream_for(jr(200, METRICS))
    assert (await client.get(PREFIX + "/metrics")).status_code == 401
    assert (await client.get(PREFIX + "/metrics", headers=user_headers)).status_code == 403
    assert upstream.requests == []

    response = await client.get(PREFIX + "/metrics", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["tasks"]["byStatus"]["QUEUED"] == 2
    assert body["queue"] == METRICS["queue"]
    assert body["engine"]["recovery"]["lastSweepAt"] is None          # unknown stays null, never becomes 0
    assert body["scheduler"] == {"enabled": False}
    assert upstream.requests[0].url.path == "/api/admin/metrics"
    assert upstream.requests[0].headers["authorization"].startswith("Bearer operator-")


async def test_metrics_unavailable_runtime_is_a_502(client, upstream_for, admin_headers):
    upstream_for(httpx.ConnectError("refused"))
    response = await client.get(PREFIX + "/metrics", headers=admin_headers)
    assert response.status_code == 502 and response.json()["detail"]["code"] == "DARIUS_UNAVAILABLE"


async def test_metrics_forbidden_for_the_operator_credential_is_not_masked(client, upstream_for, admin_headers):
    upstream_for(jr(403, {"error": "Forbidden"}))
    response = await client.get(PREFIX + "/metrics", headers=admin_headers)
    assert response.status_code in (400, 502)  # never a 200 with invented numbers
    assert "tasks" not in response.json()


async def test_malformed_metrics_body_is_a_502(client, upstream_for, admin_headers):
    upstream_for(jr(200, {"unexpected": True}))
    response = await client.get(PREFIX + "/metrics", headers=admin_headers)
    assert response.status_code == 502 and response.json()["detail"]["code"] == "DARIUS_INVALID_RESPONSE"


async def test_result_exposes_failure_class_and_retry_schedule(client, upstream_for, admin_headers):
    upstream_for(jr(200, {"id": "t-1", "status": "FAILED", "done": True, "error": "x", "failureClass": "EFFECT_UNKNOWN",
                          "updatedAt": "x"}))
    body = (await client.get(PREFIX + "/tasks/t-1/result", headers=admin_headers)).json()
    assert body["failureClass"] == "EFFECT_UNKNOWN" and body["retry"] is None

    upstream_for(jr(200, {"id": "t-2", "status": "QUEUED", "done": False, "updatedAt": "x",
                          "retry": {"attempts": 2, "nextAttemptAt": 1760900005000}}))
    body = (await client.get(PREFIX + "/tasks/t-2/result", headers=admin_headers)).json()
    assert body["retry"] == {"attempts": 2, "nextAttemptAt": 1760900005000} and body["failureClass"] is None

    upstream_for(jr(200, {"id": "t-3", "status": "COMPLETED", "done": True, "result": "r", "updatedAt": "x"}))
    body = (await client.get(PREFIX + "/tasks/t-3/result", headers=admin_headers)).json()
    assert body["failureClass"] is None and body["retry"] is None     # older runtimes keep working


# ---------------------------------------------------------------- paused conversations
@pytest.fixture
async def control_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(_migrate_control_tables_sync)


async def _contact(session_factory, name: str, phone: str) -> int:
    async with session_factory() as db:
        contact = Contact(name=name, phone=phone, preferences={})
        db.add(contact)
        await db.commit()
        return contact.id


async def _pause(session_factory, cid: int, instance: str, reason: str, actor_id: int | None, event: str):
    async with session_factory() as db:
        state = await conversation_control.pause(db, cid, instance, event, reason, actor_id)
        await db.commit()
        return state


async def test_paused_conversations_require_admin(client, control_tables, admin_headers, user_headers):
    assert (await client.get(PREFIX + "/paused-conversations")).status_code == 401
    assert (await client.get(PREFIX + "/paused-conversations", headers=user_headers)).status_code == 403
    empty = (await client.get(PREFIX + "/paused-conversations", headers=admin_headers)).json()
    assert empty == {"items": [], "total": 0, "next_offset": None}


async def test_only_paused_conversations_are_listed_with_masked_phone_reason_and_actor(
    client, control_tables, admin_headers, admin_user, session_factory,
):
    a = await _contact(session_factory, "Ana", "5511999990001")
    b = await _contact(session_factory, "Bruno", "5511999990002")
    c = await _contact(session_factory, "Carla", "5511999990003")
    await _pause(session_factory, a, "store", "dono assumiu", admin_user.id, "e-a")
    state_b = await _pause(session_factory, b, "store", "cliente pediu humano", None, "e-b")
    await _pause(session_factory, c, "personal", "outra instância", None, "e-c")
    async with session_factory() as db:                      # Bruno is resumed: must disappear from the list
        await conversation_control.resume(db, b, "store", state_b["revision"], admin_user.id)
        await db.commit()

    body = (await client.get(PREFIX + "/paused-conversations", headers=admin_headers)).json()
    assert body["total"] == 2 and body["next_offset"] is None
    by_contact = {item["contact_id"]: item for item in body["items"]}
    assert set(by_contact) == {a, c}
    ana = by_contact[a]
    assert ana["contact_name"] == "Ana" and ana["instance"] == "store"
    assert ana["phone_tail"] == "0001" and "5511999990001" not in str(body)      # never the full number
    assert ana["reason"] == "dono assumiu" and ana["actor_id"] == admin_user.id
    assert ana["send_in_flight"] is False
    since = datetime.fromisoformat(ana["paused_since"])
    assert since.utcoffset() == timedelta(0)           # explicit UTC, never a naive value the browser reads as local
    assert by_contact[c]["actor_id"] is None

    only_store = (await client.get(PREFIX + "/paused-conversations?instance=store", headers=admin_headers)).json()
    assert [i["contact_id"] for i in only_store["items"]] == [a] and only_store["total"] == 1


async def test_paused_conversations_paginate_and_reflect_the_latest_pause_reason(
    client, control_tables, admin_headers, session_factory,
):
    ids = [await _contact(session_factory, f"C{i}", f"551199999{i:04d}") for i in range(5)]
    for i, cid in enumerate(ids):
        await _pause(session_factory, cid, "store", f"motivo {i}", None, f"e-{i}")

    page1 = (await client.get(PREFIX + "/paused-conversations?limit=2&offset=0", headers=admin_headers)).json()
    page2 = (await client.get(PREFIX + "/paused-conversations?limit=2&offset=2", headers=admin_headers)).json()
    page3 = (await client.get(PREFIX + "/paused-conversations?limit=2&offset=4", headers=admin_headers)).json()
    assert [p["total"] for p in (page1, page2, page3)] == [5, 5, 5]
    assert page1["next_offset"] == 2 and page2["next_offset"] == 4 and page3["next_offset"] is None
    seen = [i["contact_id"] for p in (page1, page2, page3) for i in p["items"]]
    assert sorted(seen) == sorted(ids) and len(set(seen)) == 5          # no duplicates, no gaps

    # pause -> resume -> pause again: the reason shown is the LATEST pause
    async with session_factory() as db:
        state = await conversation_control.snapshot(db, ids[0], "store")
        await conversation_control.resume(db, ids[0], "store", state["revision"], 1)
        await db.commit()
    await _pause(session_factory, ids[0], "store", "segunda pausa", None, "e-again")
    items = (await client.get(PREFIX + "/paused-conversations?limit=200", headers=admin_headers)).json()["items"]
    assert next(i for i in items if i["contact_id"] == ids[0])["reason"] == "segunda pausa"


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1"])
async def test_paused_conversations_validate_the_query(client, control_tables, admin_headers, query):
    assert (await client.get(f"{PREFIX}/paused-conversations?{query}", headers=admin_headers)).status_code == 422


async def test_the_listing_is_read_only(client, control_tables, admin_headers, session_factory):
    cid = await _contact(session_factory, "Ana", "5511999990001")
    await _pause(session_factory, cid, "store", "x", None, "e-1")
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = await client.request(method, PREFIX + "/paused-conversations", headers=admin_headers)
        assert response.status_code == 405
    async with session_factory() as db:
        paused = (await db.execute(text("SELECT paused FROM conversation_controls"))).scalar_one()
    assert bool(paused) is True


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("slow"),
        httpx.ConnectTimeout("slow"),
        httpx.RemoteProtocolError("reset"),
        jr(500, {"e": 1}),
        jr(503, {"e": 1}),
    ],
    ids=["read-timeout", "connect-timeout", "reset", "http-500", "http-503"],
)
async def test_metrics_dependency_failures_are_502_without_numbers(client, upstream_for, admin_headers, failure):
    upstream_for(failure)
    response = await client.get(PREFIX + "/metrics", headers=admin_headers)
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "DARIUS_UNAVAILABLE"
    assert "tasks" not in response.text and "queue" not in response.text


async def test_metrics_after_a_failure_is_not_served_from_the_previous_success(client, upstream_for, admin_headers):
    """No cache and no last-known-good: the panel must see the outage, not yesterday's numbers as current."""
    upstream_for(jr(200, METRICS), httpx.ConnectError("refused"))
    first = await client.get(PREFIX + "/metrics", headers=admin_headers)
    assert first.status_code == 200
    upstream_for(httpx.ConnectError("refused"))
    second = await client.get(PREFIX + "/metrics", headers=admin_headers)
    assert second.status_code == 502 and "tasks" not in second.text


async def test_metrics_not_configured_is_an_explicit_503(client, admin_headers):
    from admin.darius import operator_client
    from main import app
    from services.darius_client import DariusClient

    app.dependency_overrides[operator_client] = lambda: DariusClient("", "")
    try:
        response = await client.get(PREFIX + "/metrics", headers=admin_headers)
    finally:
        app.dependency_overrides.pop(operator_client, None)
    assert response.status_code == 503 and response.json()["detail"]["code"] == "DARIUS_NOT_CONFIGURED"


async def test_metrics_open_circuit_fails_fast_without_calling_the_runtime(client, upstream_for, admin_headers):
    upstream = upstream_for(httpx.ConnectError("refused"))
    for _ in range(6):                       # breaker threshold is 5 consecutive failures
        assert (await client.get(PREFIX + "/metrics", headers=admin_headers)).status_code == 502
    calls = len(upstream.requests)
    response = await client.get(PREFIX + "/metrics", headers=admin_headers)
    assert response.status_code == 502 and response.json()["detail"]["code"] == "CIRCUIT_OPEN"
    assert len(upstream.requests) == calls   # failed fast: no request left the process


async def test_metrics_indicators_stay_consistent_in_the_relay(client, upstream_for, admin_headers):
    """The bridge relays; it must not break the invariants the runtime states."""
    upstream_for(jr(200, METRICS))
    body = (await client.get(PREFIX + "/metrics", headers=admin_headers)).json()
    by_status = body["tasks"]["byStatus"]
    assert body["tasks"]["total"] == sum(by_status.values())
    assert body["queue"]["queued"] == by_status["QUEUED"]
    assert 0 <= body["queue"]["backingOff"] <= body["queue"]["queued"]