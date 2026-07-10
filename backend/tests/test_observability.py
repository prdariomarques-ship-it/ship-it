import pytest


@pytest.mark.asyncio
async def test_liveness(client):
    for path in ("/health", "/health/live"):
        response = await client.get(path)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_reports_dependency_status(client):
    response = await client.get("/health/ready")
    body = response.json()
    assert set(body["checks"]) == {"database", "redis", "qdrant", "whatsapp"}
    # Redis/Qdrant/WhatsApp are optional: without them the service is degraded, not down.
    assert body["status"] in {"ok", "degraded", "unavailable"}


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_format(client):
    await client.get("/health")  # generate at least one request metric
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "darioos_http_requests_total" in response.text
