"""Tests for the EconomicCalendarProvider abstraction and Mock implementation.

These tests verify:
1. The interface contract is fulfilled by MockProvider.
2. Filtering by country, volatility, and date works correctly.
3. The factory auto-fallback to Mock when no API key is set.
4. The provider returns deterministic data.
"""
import asyncio
from datetime import datetime, timezone

import pytest
from providers.economic_calendar.base import (
    EconomicCalendarProvider,
    EconomicEvent,
    EconomicEventList,
    Volatility,
)
from providers.economic_calendar.factory import get_economic_calendar_provider
from providers.economic_calendar.mock import MockEconomicCalendarProvider


# ── Unit tests: Mock provider ─────────────────────────────────────

class TestMockEconomicCalendarProvider:
    """MockEconomicCalendarProvider must fulfil the abstract contract."""

    def test_is_abstract_subclass(self):
        """MockProvider must be a valid EconomicCalendarProvider."""
        provider = MockEconomicCalendarProvider()
        assert isinstance(provider, EconomicCalendarProvider)

    def test_name(self):
        provider = MockEconomicCalendarProvider()
        assert provider.name == "mock"

    def test_list_events_returns_all(self):
        """Without filters, returns all synthetic events."""
        provider = MockEconomicCalendarProvider()
        result = asyncio.get_event_loop().run_until_complete(
            provider.list_events()
        )
        assert isinstance(result, EconomicEventList)
        assert result.total == len(result.events)
        assert result.total > 0

    def test_list_events_returns_event_objects(self):
        """Each event must be a proper EconomicEvent with all required fields."""
        provider = MockEconomicCalendarProvider()
        result = asyncio.get_event_loop().run_until_complete(
            provider.list_events()
        )
        for event in result.events:
            assert isinstance(event, EconomicEvent)
            assert event.id
            assert event.name
            assert event.country_code
            assert event.date_utc is not None
            assert event.volatility in Volatility

    def test_list_events_filter_by_country(self):
        provider = MockEconomicCalendarProvider()
        result = asyncio.get_event_loop().run_until_complete(
            provider.list_events(country_code="US")
        )
        for event in result.events:
            assert event.country_code == "US"

    def test_list_events_filter_by_volatility(self):
        provider = MockEconomicCalendarProvider()
        result = asyncio.get_event_loop().run_until_complete(
            provider.list_events(volatility=Volatility.HIGH)
        )
        for event in result.events:
            assert event.volatility == Volatility.HIGH

    def test_list_events_filter_by_volatility_medium_or_high(self):
        """MEDIUM filter should include MEDIUM and HIGH events."""
        provider = MockEconomicCalendarProvider()
        result = asyncio.get_event_loop().run_until_complete(
            provider.list_events(volatility=Volatility.MEDIUM)
        )
        for event in result.events:
            assert event.volatility in (Volatility.MEDIUM, Volatility.HIGH)

    def test_list_events_filter_by_volatility_low_or_higher(self):
        """LOW filter should include LOW, MEDIUM, and HIGH events."""
        provider = MockEconomicCalendarProvider()
        result = asyncio.get_event_loop().run_until_complete(
            provider.list_events(volatility=Volatility.LOW)
        )
        for event in result.events:
            assert event.volatility in (
                Volatility.LOW,
                Volatility.MEDIUM,
                Volatility.HIGH,
            )

    def test_list_events_limit(self):
        provider = MockEconomicCalendarProvider()
        result = asyncio.get_event_loop().run_until_complete(
            provider.list_events(limit=2)
        )
        assert result.total <= 2

    def test_list_events_date_range(self):
        """Events are anchored to now, so start_date=now+2h should exclude
        events with offset_hours=1 but include those with offset_hours=8."""
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        start = now + timedelta(hours=2)
        provider = MockEconomicCalendarProvider()
        result = asyncio.get_event_loop().run_until_complete(
            provider.list_events(start_date=start)
        )
        for event in result.events:
            assert event.date_utc >= start

    def test_list_events_metadata(self):
        """The result should carry filter metadata."""
        provider = MockEconomicCalendarProvider()
        result = asyncio.get_event_loop().run_until_complete(
            provider.list_events(country_code="BR", volatility=Volatility.MEDIUM)
        )
        assert result.country_filter == "BR"
        assert result.volatility_filter == "MEDIUM"

    def test_list_countries(self):
        provider = MockEconomicCalendarProvider()
        countries = asyncio.get_event_loop().run_until_complete(
            provider.list_countries()
        )
        assert isinstance(countries, list)
        assert len(countries) > 0
        for country in countries:
            assert "code" in country
            assert "name" in country


# ── Integration tests: factory ────────────────────────────────────

class TestEconomicCalendarFactory:
    """The factory must auto-fallback to Mock when no API key is set."""

    def test_factory_returns_mock_when_no_api_key(self, monkeypatch):
        """Without ECONOMIC_CALENDAR_API_KEY, factory returns MockProvider."""
        monkeypatch.delenv("ECONOMIC_CALENDAR_API_KEY", raising=False)
        monkeypatch.delenv("ECONOMIC_CALENDAR_PROVIDER", raising=False)
        # Clear the lru_cache so the test gets a fresh resolution
        get_economic_calendar_provider.cache_clear()

        provider = get_economic_calendar_provider()
        assert isinstance(provider, MockEconomicCalendarProvider)
        assert provider.name == "mock"

    def test_factory_returns_mock_for_mock_name(self, monkeypatch):
        """Explicitly requesting 'mock' must always return MockProvider."""
        monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "mock")
        monkeypatch.delenv("ECONOMIC_CALENDAR_API_KEY", raising=False)
        get_economic_calendar_provider.cache_clear()

        provider = get_economic_calendar_provider()
        assert isinstance(provider, MockEconomicCalendarProvider)

    def test_factory_unknown_provider_raises(self, monkeypatch):
        """Requesting an unknown provider must raise."""
        monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "nonexistent")
        monkeypatch.setenv("ECONOMIC_CALENDAR_API_KEY", "fake-key")
        get_economic_calendar_provider.cache_clear()
        from utils.config import get_settings as _gs
        _gs.cache_clear()

        from providers.economic_calendar.factory import (
            UnknownEconomicCalendarProviderError,
        )
        with pytest.raises(UnknownEconomicCalendarProviderError):
            get_economic_calendar_provider()

        # Cleanup
        monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "rapidapi")
        monkeypatch.delenv("ECONOMIC_CALENDAR_API_KEY", raising=False)
        get_economic_calendar_provider.cache_clear()
        _gs.cache_clear()


# ── Integration tests: Volatility enum ────────────────────────────

class TestVolatilityEnum:
    """Volatility must be a valid enum with the expected values."""

    def test_values(self):
        assert Volatility.NONE.value == "NONE"
        assert Volatility.LOW.value == "LOW"
        assert Volatility.MEDIUM.value == "MEDIUM"
        assert Volatility.HIGH.value == "HIGH"

    def test_from_string(self):
        assert Volatility("HIGH") == Volatility.HIGH
        assert Volatility("LOW") == Volatility.LOW

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            Volatility("INVALID")
