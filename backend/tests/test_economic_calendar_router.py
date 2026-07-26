"""Integration tests for the Economic Calendar API endpoints.

Tests the FastAPI router directly using TestClient to verify:
1. GET /api/economic-calendar/events returns valid JSON
2. GET /api/economic-calendar/countries returns valid JSON
3. Query parameters are properly forwarded to the service
4. Response structure matches the schema
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from providers.economic_calendar.base import (
    EconomicEvent,
    EconomicEventList,
    Volatility,
)


def _sample_event_list() -> EconomicEventList:
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    events = [
        EconomicEvent(
            id="nfp-2026",
            name="Non-Farm Payrolls",
            country_code="US",
            country_name="United States",
            currency="USD",
            date_utc=now + timedelta(hours=8),
            volatility=Volatility.HIGH,
            actual="216K",
            forecast="200K",
            previous="199K",
            unit="Jobs",
            category="Employment",
        ),
        EconomicEvent(
            id="cpi-2026",
            name="Consumer Price Index (YoY)",
            country_code="US",
            country_name="United States",
            currency="USD",
            date_utc=now + timedelta(hours=24),
            volatility=Volatility.HIGH,
            actual="3.2%",
            forecast="3.3%",
            previous="3.4%",
            unit="Percent",
            category="Inflation",
        ),
    ]
    return EconomicEventList(events=events, total=len(events))


class TestEconomicCalendarEventsEndpoint:
    """GET /api/economic-calendar/events"""

    @pytest.mark.asyncio
    async def test_returns_events_with_mock_provider(self):
        """Endpoint returns valid JSON with events from the mock provider."""
        from main import create_app

        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/economic-calendar/events")

        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "total" in data
        assert data["total"] > 0
        assert isinstance(data["events"], list)

    @pytest.mark.asyncio
    async def test_events_have_required_fields(self):
        """Each event in the response has all required fields."""
        from main import create_app

        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/economic-calendar/events")

        assert resp.status_code == 200
        data = resp.json()
        for event in data["events"]:
            assert "id" in event
            assert "name" in event
            assert "country_code" in event
            assert "date_utc" in event
            assert "volatility" in event
            assert event["volatility"] in ("NONE", "LOW", "MEDIUM", "HIGH")

    @pytest.mark.asyncio
    async def test_filter_by_country(self):
        """Passing country_code filters the results."""
        from main import create_app

        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/economic-calendar/events",
                params={"country_code": "BR"},
            )

        assert resp.status_code == 200
        data = resp.json()
        for event in data["events"]:
            assert event["country_code"] == "BR"

    @pytest.mark.asyncio
    async def test_filter_by_volatility(self):
        """Passing volatility filters the results."""
        from main import create_app

        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/economic-calendar/events",
                params={"volatility": "HIGH"},
            )

        assert resp.status_code == 200
        data = resp.json()
        for event in data["events"]:
            assert event["volatility"] == "HIGH"

    @pytest.mark.asyncio
    async def test_limit_parameter(self):
        """Limit parameter restricts the number of events returned."""
        from main import create_app

        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/economic-calendar/events",
                params={"limit": 1},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] <= 1

    @pytest.mark.asyncio
    async def test_response_has_metadata(self):
        """Response includes filter metadata."""
        from main import create_app

        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/economic-calendar/events",
                params={"country_code": "US", "volatility": "HIGH"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["country_filter"] == "US"
        assert data["volatility_filter"] == "HIGH"


class TestEconomicCalendarCountriesEndpoint:
    """GET /api/economic-calendar/countries"""

    @pytest.mark.asyncio
    async def test_returns_countries(self):
        """Endpoint returns a list of countries."""
        from main import create_app

        app = create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/economic-calendar/countries")

        assert resp.status_code == 200
        data = resp.json()
        assert "countries" in data
        assert "total" in data
        assert data["total"] > 0
        for country in data["countries"]:
            assert "code" in country
            assert "name" in country
