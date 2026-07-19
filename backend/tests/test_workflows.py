"""Coverage for /api/workflows/{workflow_name}/trigger — the only endpoint
in workflows_router. Zero coverage existed before this file. Mocks
httpx.AsyncClient the same way test_google_http.py does, since
WorkflowService talks to n8n over plain HTTP with no shared retry helper
of its own (the module docstring notes queue-level retry, via
jobs.handlers.trigger_workflow, covers transient n8n outages instead).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from workflows.service import WorkflowError, workflow_service


def _json_response(status_code: int = 200, body: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = {"content-type": "application/json"}
    response.json = MagicMock(return_value=body if body is not None else {"ok": True})
    response.raise_for_status = MagicMock()
    return response


def _non_json_response(status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = {"content-type": "text/plain"}
    response.raise_for_status = MagicMock()
    return response


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    response = MagicMock()
    response.status_code = status_code
    response.headers = {}
    error = httpx.HTTPStatusError("error", request=MagicMock(), response=response)
    raised_response = MagicMock()
    raised_response.status_code = status_code
    raised_response.headers = {"content-type": "application/json"}
    raised_response.raise_for_status = MagicMock(side_effect=error)
    return raised_response


def _patch_client(post_result) -> tuple:
    client = MagicMock()
    client.post = AsyncMock(return_value=post_result)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return patch("workflows.service.httpx.AsyncClient", return_value=client), client


async def _create_second_user(client, admin_headers, email: str) -> dict[str, str]:
    """Non-admin account, via the admin-only creation endpoint (public
    registration is closed after the bootstrap account, see test_auth.py)."""
    await client.post(
        "/api/admin/users",
        json={"email": email, "full_name": "User", "password": "supersecret1"},
        headers=admin_headers,
    )
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": "supersecret1"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# --- Success path -----------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_workflow_success(client, auth_headers):
    patcher, mock_client = _patch_client(_json_response(body={"executed": True}))
    with patcher:
        response = await client.post(
            "/api/workflows/daily-briefing/trigger",
            json={"payload": {"foo": "bar"}},
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow"] == "daily-briefing"
    assert body["result"] == {"executed": True}
    mock_client.post.assert_awaited_once()
    call_args = mock_client.post.await_args
    assert call_args.args[0] == "http://localhost:5678/webhook/daily-briefing"
    assert call_args.kwargs["json"] == {"foo": "bar"}


@pytest.mark.asyncio
async def test_trigger_workflow_non_json_response_falls_back_to_status_ok(
    client, auth_headers
):
    patcher, _ = _patch_client(_non_json_response())
    with patcher:
        response = await client.post(
            "/api/workflows/some-workflow/trigger",
            json={"payload": {}},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["result"] == {"status": "ok"}


# --- Authentication -----------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_workflow_requires_authentication(client):
    response = await client.post(
        "/api/workflows/daily-briefing/trigger", json={"payload": {}}
    )
    assert response.status_code == 401


# --- Authorization --------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_workflow_allows_any_authenticated_user(client, auth_headers):
    """No admin-only restriction exists on this endpoint today — a plain
    USER account (created via the admin-only endpoint, not self-registered)
    must succeed just like the admin does. Documents the current
    authorization model so a future accidental tightening/loosening shows
    up here."""
    user_headers = await _create_second_user(client, auth_headers, "worker@example.com")

    patcher, _ = _patch_client(_json_response())
    with patcher:
        response = await client.post(
            "/api/workflows/daily-briefing/trigger",
            json={"payload": {}},
            headers=user_headers,
        )

    assert response.status_code == 200


# --- Invalid payload / missing parameters ----------------------------------


@pytest.mark.asyncio
async def test_trigger_workflow_invalid_payload_type_rejected(client, auth_headers):
    response = await client.post(
        "/api/workflows/daily-briefing/trigger",
        json={"payload": "not-a-dict"},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_trigger_workflow_missing_body_uses_default_empty_payload(
    client, auth_headers
):
    patcher, mock_client = _patch_client(_json_response())
    with patcher:
        response = await client.post(
            "/api/workflows/daily-briefing/trigger",
            json={},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert mock_client.post.await_args.kwargs["json"] == {}


@pytest.mark.asyncio
async def test_trigger_workflow_no_body_at_all_rejected(client, auth_headers):
    """No JSON body at all (not even `{}`) fails request validation --
    distinct from an empty object, which is handled by the default above."""
    response = await client.post(
        "/api/workflows/daily-briefing/trigger",
        headers=auth_headers,
    )
    assert response.status_code == 422


# --- Nonexistent resource / exception handling -----------------------------


@pytest.mark.asyncio
async def test_trigger_workflow_nonexistent_workflow_returns_502(client, auth_headers):
    """n8n has no webhook registered for this name -> 404 from n8n itself,
    collapsed by WorkflowService into a generic WorkflowError -> 502. Not a
    passthrough 404 -- worth asserting explicitly since it's easy to expect
    the wrong status code here."""
    patcher, _ = _patch_client(_http_status_error(404))
    with patcher:
        response = await client.post(
            "/api/workflows/does-not-exist/trigger",
            json={"payload": {}},
            headers=auth_headers,
        )

    assert response.status_code == 502
    assert "does-not-exist" in response.json()["detail"]


@pytest.mark.asyncio
async def test_trigger_workflow_n8n_unreachable_returns_502(client, auth_headers):
    client_mock = MagicMock()
    client_mock.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=False)

    with patch("workflows.service.httpx.AsyncClient", return_value=client_mock):
        response = await client.post(
            "/api/workflows/daily-briefing/trigger",
            json={"payload": {}},
            headers=auth_headers,
        )

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_trigger_workflow_n8n_timeout_returns_502(client, auth_headers):
    client_mock = MagicMock()
    client_mock.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=False)

    with patch("workflows.service.httpx.AsyncClient", return_value=client_mock):
        response = await client.post(
            "/api/workflows/daily-briefing/trigger",
            json={"payload": {}},
            headers=auth_headers,
        )

    assert response.status_code == 502


# --- Edge cases -------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_workflow_empty_name_path_not_found(client, auth_headers):
    """An empty {workflow_name} path segment doesn't match this route at
    all -- FastAPI 404s before the handler ever runs."""
    response = await client.post(
        "/api/workflows//trigger", json={"payload": {}}, headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_trigger_workflow_name_with_special_characters(client, auth_headers):
    patcher, mock_client = _patch_client(_json_response())
    with patcher:
        response = await client.post(
            "/api/workflows/my-workflow_v2/trigger",
            json={"payload": {}},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["workflow"] == "my-workflow_v2"
    assert mock_client.post.await_args.args[0].endswith("/webhook/my-workflow_v2")


@pytest.mark.asyncio
async def test_trigger_workflow_service_raises_workflow_error_directly(client, auth_headers):
    """Exercises the router's except WorkflowError branch directly,
    independent of WorkflowService's own httpx mocking above."""
    with patch.object(
        workflow_service, "trigger", AsyncMock(side_effect=WorkflowError("boom"))
    ):
        response = await client.post(
            "/api/workflows/daily-briefing/trigger",
            json={"payload": {}},
            headers=auth_headers,
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "boom"
