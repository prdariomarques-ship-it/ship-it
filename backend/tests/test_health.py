import asyncio
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "Dario OS"


@pytest.mark.asyncio
async def test_openapi_available(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/auth/login" in response.json()["paths"]


def _ready_checks_patch(
    *, database=True, redis=True, qdrant=True, whatsapp=True, google=True
):
    """Patch each dependency check to succeed/fail per the given flags,
    without touching the real database/Redis/Qdrant/WhatsApp/Google state."""

    def _ok():
        return AsyncMock(return_value="ok")

    def _fail():
        return AsyncMock(side_effect=RuntimeError("simulated dependency failure"))

    return patch.multiple(
        "observability.health",
        _check_database=_ok() if database else _fail(),
        _check_redis=_ok() if redis else _fail(),
        _check_qdrant=_ok() if qdrant else _fail(),
        _check_whatsapp=_ok() if whatsapp else _fail(),
        _check_google=_ok() if google else _fail(),
    )


@pytest.mark.asyncio
async def test_readiness_all_healthy(client):
    with _ready_checks_patch():
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {
        "database": "ok",
        "redis": "ok",
        "qdrant": "ok",
        "whatsapp": "ok",
        "google": "ok",
    }


@pytest.mark.asyncio
async def test_readiness_required_dependency_down_returns_503(client):
    """database is the one required dependency — its failure must fail readiness."""
    with _ready_checks_patch(database=False):
        response = await client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"].startswith("error")


@pytest.mark.asyncio
async def test_readiness_optional_dependency_down_degrades_not_fails(client):
    """redis/qdrant/whatsapp/google are optional — failing must degrade, not 503."""
    with _ready_checks_patch(redis=False):
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["redis"].startswith("error")
    assert body["checks"]["database"] == "ok"


@pytest.mark.asyncio
async def test_readiness_multiple_optional_dependencies_down_still_degrades(client):
    with _ready_checks_patch(redis=False, qdrant=False, whatsapp=False):
        response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


@pytest.mark.asyncio
async def test_readiness_slow_dependency_times_out_as_error(client):
    """Each check is bounded to 5s (asyncio.wait_for) — a dependency that
    hangs must show up as a timeout error, not hang the whole endpoint."""

    async def _hangs():
        await asyncio.sleep(30)
        return "ok"

    with patch.multiple(
        "observability.health",
        _check_database=AsyncMock(return_value="ok"),
        _check_redis=_hangs,
        _check_qdrant=AsyncMock(return_value="ok"),
        _check_whatsapp=AsyncMock(return_value="ok"),
        _check_google=AsyncMock(return_value="ok"),
    ):
        response = await asyncio.wait_for(client.get("/health/ready"), timeout=8)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert "TimeoutError" in body["checks"]["redis"]


@pytest.mark.asyncio
async def test_readiness_reports_open_google_circuits_as_degraded(client, monkeypatch):
    """_check_google reads real in-memory circuit state (providers/
    google_http.py) rather than making a network call -- verify that
    end-to-end, not just via the generic _fail() mock used elsewhere."""
    from providers import google_http

    monkeypatch.setitem(
        google_http._circuits,
        "gmail",
        google_http._CircuitState(opened_at=1.0),
    )

    with patch.multiple(
        "observability.health",
        _check_database=AsyncMock(return_value="ok"),
        _check_redis=AsyncMock(return_value="ok"),
        _check_qdrant=AsyncMock(return_value="ok"),
        _check_whatsapp=AsyncMock(return_value="ok"),
    ):
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["google"] == "error: GoogleCircuitsOpenError"
