"""Economic Calendar service — the ONLY entry point for business logic.

No caller should ever import a specific provider directly; they call
``EconomicCalendarService`` which delegates to whatever provider the
factory returned.  This is the single rule that keeps the provider
pattern working.

The service also implements caching: economic calendar data changes
slowly (5-minute refresh cycle on the upstream), so we cache the
response for a configurable TTL to avoid hammering the API.
"""
from datetime import datetime, timezone, timedelta
from providers.economic_calendar.base import (
    EconomicCalendarProviderError,
    EconomicEvent,
    EconomicEventList,
    Volatility,
)
from providers.economic_calendar.factory import get_economic_calendar_provider
from services.cache import cache_service
from utils.logging import get_logger

logger = get_logger(__name__)

_CACHE_KEY_PREFIX = "economic_calendar:"
_CACHE_TTL_SECONDS = 300  # 5 minutes, matching upstream refresh cycle


class EconomicCalendarService:
    """Singleton-ish service facade over EconomicCalendarProvider."""

    @classmethod
    async def list_events(
        cls,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        country_code: str | None = None,
        volatility: str | None = None,
        limit: int = 100,
    ) -> EconomicEventList:
        """Fetch economic events with caching.

        Parameters are strings (from the API query params) and get
        parsed/validated here before passing to the provider.
        """
        # Build cache key from all filter params
        cache_key = _build_cache_key(
            start_date, end_date, country_code, volatility, limit
        )

        # Try cache first
        cached = await cache_service.get(cache_key)
        if cached is not None:
            logger.debug("Economic calendar cache hit: %s", cache_key)
            return EconomicEventList(**cached)

        # Parse dates
        parsed_start = _parse_date(start_date)
        parsed_end = _parse_date(end_date)
        parsed_volatility = _parse_volatility(volatility)

        # Delegate to provider
        provider = get_economic_calendar_provider()
        logger.info(
            "Fetching economic calendar from %s (start=%s, end=%s, country=%s, "
            "volatility=%s, limit=%d)",
            provider.name,
            parsed_start,
            parsed_end,
            country_code,
            volatility,
            limit,
        )

        try:
            result = await provider.list_events(
                start_date=parsed_start,
                end_date=parsed_end,
                country_code=country_code,
                volatility=parsed_volatility,
                limit=limit,
            )
        except EconomicCalendarProviderError as exc:
            logger.error("Economic calendar provider error: %s", exc)
            # Return empty result on failure — never crash the dashboard
            return EconomicEventList(
                events=[],
                total=0,
                from_date=parsed_start.strftime("%Y-%m-%d") if parsed_start else None,
                to_date=parsed_end.strftime("%Y-%m-%d") if parsed_end else None,
                country_filter=country_code,
                volatility_filter=volatility,
            )

        # Cache the result
        await cache_service.set(cache_key, result.model_dump(), ttl_seconds=_CACHE_TTL_SECONDS)

        return result

    @classmethod
    async def list_countries(cls) -> list[dict[str, str]]:
        """Fetch the list of supported countries."""
        cache_key = f"{_CACHE_KEY_PREFIX}countries"

        cached = await cache_service.get(cache_key)
        if cached is not None:
            return cached

        provider = get_economic_calendar_provider()
        try:
            countries = await provider.list_countries()
        except EconomicCalendarProviderError as exc:
            logger.error("Economic calendar countries error: %s", exc)
            # Return a sensible default list on failure
            return [
                {"code": "US", "name": "United States"},
                {"code": "EU", "name": "Eurozone"},
                {"code": "BR", "name": "Brazil"},
                {"code": "GB", "name": "United Kingdom"},
                {"code": "JP", "name": "Japan"},
                {"code": "CN", "name": "China"},
            ]

        await cache_service.set(cache_key, countries, ttl_seconds=3600)  # 1 hour
        return countries


# ── Helpers ────────────────────────────────────────────────────────

def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning("Invalid date format: %s, expected YYYY-MM-DD", value)
        return None


def _parse_volatility(value: str | None) -> Volatility | None:
    if not value:
        return None
    try:
        return Volatility(value.upper())
    except ValueError:
        logger.warning("Invalid volatility: %s, ignoring filter", value)
        return None


def _build_cache_key(
    start_date: str | None,
    end_date: str | None,
    country_code: str | None,
    volatility: str | None,
    limit: int,
) -> str:
    parts = [
        start_date or "today",
        end_date or "7d",
        country_code or "all",
        volatility or "all",
        str(limit),
    ]
    return f"{_CACHE_KEY_PREFIX}{':'.join(parts)}"
