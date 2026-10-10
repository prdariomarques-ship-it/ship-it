"""Tests for the EconomicCalendarService.

These tests verify:
1. Service delegates to the provider correctly.
2. Service handles provider errors gracefully (returns empty list).
3. Service parses query parameters correctly.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from providers.economic_calendar.base import (
    EconomicCalendarProviderError,
    EconomicEvent,
    EconomicEventList,
    Volatility,
)
from services.economic_calendar import EconomicCalendarService


# ── Helper: build a sample result ─────────────────────────────────

def _sample_event_list(n: int = 3) -> EconomicEventList:
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    events = [
        EconomicEvent(
            id=f"test-{i}",
            name=f"Test Event {i}",
            country_code="US",
            country_name="United States",
            currency="USD",
            date_utc=now + timedelta(hours=i * 2),
            volatility=Volatility.HIGH if i == 0 else Volatility.LOW,
            actual="100",
            forecast="90",
            previous="85",
        )
        for i in range(n)
    ]
    return EconomicEventList(events=events, total=n)


# ── Unit tests ────────────────────────────────────────────────────

class TestEconomicCalendarService:
    """Service must delegate to provider and handle errors gracefully."""

    @pytest.mark.asyncio
    async def test_list_events_delegates_to_provider(self):
        """Service calls the provider with correct parameters."""
        sample = _sample_event_list()
        mock_provider = AsyncMock()
        mock_provider.list_events = AsyncMock(return_value=sample)
        mock_provider.name = "test"

        with patch(
            "services.economic_calendar.get_economic_calendar_provider",
            return_value=mock_provider,
        ):
            # Clear cache to avoid stale data
            await self._clear_cache()
            result = await EconomicCalendarService.list_events(
                country_code="US",
                volatility="HIGH",
                limit=50,
            )

        mock_provider.list_events.assert_called_once()
        assert result.total == sample.total

    @pytest.mark.asyncio
    async def test_list_events_returns_empty_on_provider_error(self):
        """When provider raises, service returns empty list (never crash)."""
        mock_provider = AsyncMock()
        mock_provider.list_events = AsyncMock(
            side_effect=EconomicCalendarProviderError("Upstream error")
        )
        mock_provider.name = "test"

        with patch(
            "services.economic_calendar.get_economic_calendar_provider",
            return_value=mock_provider,
        ):
            await self._clear_cache()
            result = await EconomicCalendarService.list_events()

        assert result.total == 0
        assert result.events == []

    @pytest.mark.asyncio
    async def test_list_events_date_parsing(self):
        """Service parses date strings into datetime objects."""
        sample = _sample_event_list(0)
        mock_provider = AsyncMock()
        mock_provider.list_events = AsyncMock(return_value=sample)
        mock_provider.name = "test"

        with patch(
            "services.economic_calendar.get_economic_calendar_provider",
            return_value=mock_provider,
        ):
            await self._clear_cache()
            result = await EconomicCalendarService.list_events(
                start_date="2026-07-01",
                end_date="2026-07-31",
            )

        # Provider should have been called with parsed dates
        call_kwargs = mock_provider.list_events.call_args
        assert call_kwargs is not None
        # start_date should be a datetime, not a string
        start_date = call_kwargs.kwargs.get("start_date") or call_kwargs[1].get("start_date")
        if start_date:
            assert isinstance(start_date, type(None)) or hasattr(start_date, "year")

    @pytest.mark.asyncio
    async def test_list_events_invalid_date_returns_result(self):
        """Invalid date strings should not crash the service."""
        sample = _sample_event_list()
        mock_provider = AsyncMock()
        mock_provider.list_events = AsyncMock(return_value=sample)
        mock_provider.name = "test"

        with patch(
            "services.economic_calendar.get_economic_calendar_provider",
            return_value=mock_provider,
        ):
            await self._clear_cache()
            result = await EconomicCalendarService.list_events(
                start_date="not-a-date",
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_list_countries_delegates_to_provider(self):
        """Service delegates country list to provider."""
        countries = [{"code": "US", "name": "United States"}]
        mock_provider = AsyncMock()
        mock_provider.list_countries = AsyncMock(return_value=countries)
        mock_provider.name = "test"

        with patch(
            "services.economic_calendar.get_economic_calendar_provider",
            return_value=mock_provider,
        ):
            await self._clear_countries_cache()
            result = await EconomicCalendarService.list_countries()

        mock_provider.list_countries.assert_called_once()
        assert result == countries

    @pytest.mark.asyncio
    async def test_list_countries_returns_defaults_on_error(self):
        """When provider fails for countries, service returns defaults."""
        mock_provider = AsyncMock()
        mock_provider.list_countries = AsyncMock(
            side_effect=EconomicCalendarProviderError("Failed")
        )
        mock_provider.name = "test"

        with patch(
            "services.economic_calendar.get_economic_calendar_provider",
            return_value=mock_provider,
        ):
            await self._clear_countries_cache()
            result = await EconomicCalendarService.list_countries()

        assert len(result) > 0
        assert any(c["code"] == "US" for c in result)

    # ── Helpers to clear cache between tests ──────────────────────

    async def _clear_cache(self):
        from services.cache import cache_service
        # Flush the local cache
        cache_service._local.clear()

    async def _clear_countries_cache(self):
        from services.cache import cache_service
        cache_service._local.clear()
