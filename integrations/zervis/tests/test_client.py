import httpx
import pytest

from zervis_bridge.client import DarioOSClient, DarioOSError


def make(handler, attempts=3):
    return DarioOSClient(
        "http://api/api",
        "tok" * 8,
        max_attempts=attempts,
        backoff=0,
        transport=httpx.MockTransport(handler),
    )


async def test_sends_bearer_and_returns_json():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"ok": 1}])

    client = make(handler)
    assert await client.get("/admin/status", {"limit": 5}) == [{"ok": 1}]
    assert seen["auth"] == "Bearer " + "tok" * 8
    assert seen["url"] == "http://api/api/admin/status?limit=5"


async def test_retries_5xx_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        return (
            httpx.Response(503)
            if len(calls) < 3
            else httpx.Response(200, json={"a": 1})
        )

    assert await make(handler).get("/x") == {"a": 1}
    assert len(calls) == 3


@pytest.mark.parametrize("status", [401, 403, 404, 422])
async def test_4xx_is_not_retried(status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status)

    with pytest.raises(DarioOSError, match=str(status)):
        await make(handler).get("/x")
    assert len(calls) == 1


async def test_transport_errors_exhaust_attempts():
    def handler(request):
        raise httpx.ConnectError("down")

    with pytest.raises(DarioOSError, match="indisponível"):
        await make(handler, attempts=2).get("/x")


async def test_error_message_never_contains_the_token():
    def handler(request):
        return httpx.Response(500, text="Bearer " + "tok" * 8)

    with pytest.raises(DarioOSError) as err:
        await make(handler).get("/x")
    assert "tok" * 8 not in str(err.value)
