import asyncio
import json
from contextlib import asynccontextmanager

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from tests.conftest import MCP_TOKEN
from zervis_bridge.app import create_app
from zervis_bridge.client import DarioOSClient


def darioos(handler):
    return DarioOSClient(
        "http://darioos/api",
        "d" * 32,
        max_attempts=1,
        backoff=0,
        transport=httpx.MockTransport(handler),
    )


@asynccontextmanager
async def serve(settings, monkeypatch):
    """App real (lifespan incluso) atrás de um ASGITransport; Redis desligado."""
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/admin/status"):
            return httpx.Response(200, json=[{"name": "db", "status": "ok"}])
        return httpx.Response(403)

    async def no_redis(self):
        await asyncio.sleep(3600)

    monkeypatch.setattr("zervis_bridge.subscriber.EventSubscriber.run", no_redis)
    app = create_app(settings, client=darioos(handler))
    async with app.router.lifespan_context(app):
        yield httpx.ASGITransport(app=app), calls


async def test_requests_without_valid_bearer_are_rejected(settings, monkeypatch):
    async with serve(settings, monkeypatch) as (transport, _):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://bridge"
        ) as http:
            assert (await http.post("/mcp", json={})).status_code == 401
            bad = await http.post(
                "/mcp", json={}, headers={"Authorization": "Bearer nope"}
            )
            assert bad.status_code == 401
            basic = await http.post(
                "/mcp", json={}, headers={"Authorization": f"Basic {MCP_TOKEN}"}
            )
            assert basic.status_code == 401


async def test_healthz_is_public_and_leaks_nothing(settings, monkeypatch):
    async with serve(settings, monkeypatch) as (transport, _):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://bridge"
        ) as http:
            response = await http.get("/healthz")
    assert response.status_code == 200 and response.json() == {"ok": True}


async def test_mcp_roundtrip_lists_only_read_tools_and_calls_darioos(
    settings, monkeypatch
):
    async with serve(settings, monkeypatch) as (transport, calls):

        def factory(headers=None, timeout=None, auth=None):
            return httpx.AsyncClient(
                transport=transport, headers=headers, timeout=timeout, auth=auth
            )

        headers = {"Authorization": f"Bearer {MCP_TOKEN}"}
        async with streamablehttp_client(
            "http://bridge/mcp", headers=headers, httpx_client_factory=factory
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {t.name for t in (await session.list_tools()).tools}
                assert tools == {
                    "darioos_status",
                    "darioos_agents",
                    "darioos_executions",
                    "darioos_context",
                    "darioos_goals",
                    "darioos_goals_ready",
                    "darioos_tasks",
                    "darioos_recent_events",
                }
                result = await session.call_tool("darioos_status", {})
                payload = json.loads(result.content[0].text)
                assert payload["components"] == [{"name": "db", "status": "ok"}]
                assert payload["bridge"]["latest_event_seq"] == 0

                denied = await session.call_tool("darioos_agents", {})
                assert "error" in json.loads(denied.content[0].text)

        assert calls and all(call.method == "GET" for call in calls)
        assert all(
            call.headers["authorization"] == "Bearer " + "d" * 32 for call in calls
        )


async def test_unlisted_host_header_is_refused_even_with_a_valid_token(
    settings, monkeypatch
):
    async with serve(settings, monkeypatch) as (transport, _):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://evil.example"
        ) as http:
            response = await http.post(
                "/mcp", json={}, headers={"Authorization": f"Bearer {MCP_TOKEN}"}
            )
    assert response.status_code == 421
