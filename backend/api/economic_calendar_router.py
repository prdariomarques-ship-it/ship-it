"""Economic Calendar API router.

Endpoints:
- GET /api/economic-calendar/events  — list economic events with filters
- GET /api/economic-calendar/countries — list supported countries

Both are public (no auth required) since economic data is public information.
"""
from fastapi import APIRouter, Query
from services.economic_calendar import EconomicCalendarService
from api.economic_calendar_schemas import (
    EconomicEventListResponse,
    EconomicEventResponse,
    EconomicCalendarCountriesResponse,
    CountryInfo,
)

router = APIRouter(prefix="/economic-calendar", tags=["economic-calendar"])


@router.get("/events", response_model=EconomicEventListResponse)
async def get_economic_events(
    start_date: str | None = Query(
        default=None,
        description="Start date (YYYY-MM-DD). Defaults to today.",
    ),
    end_date: str | None = Query(
        default=None,
        description="End date (YYYY-MM-DD). Defaults to 7 days ahead.",
    ),
    country_code: str | None = Query(
        default=None,
        description="Filter by ISO country code (e.g. US, BR, EU).",
    ),
    volatility: str | None = Query(
        default=None,
        description="Filter by minimum volatility (NONE, LOW, MEDIUM, HIGH).",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of events to return.",
    ),
) -> EconomicEventListResponse:
    """List economic calendar events.

    Returns structured macroeconomic events from the configured provider.
    If no API key is set, returns mock data automatically.
    """
    result = await EconomicCalendarService.list_events(
        start_date=start_date,
        end_date=end_date,
        country_code=country_code,
        volatility=volatility,
        limit=limit,
    )

    # Convert datetime objects to ISO strings for JSON serialization
    events = []
    for evt in result.events:
        events.append(
            EconomicEventResponse(
                id=evt.id,
                name=evt.name,
                country_code=evt.country_code,
                country_name=evt.country_name,
                currency=evt.currency,
                date_utc=evt.date_utc.isoformat(),
                volatility=evt.volatility.value,
                actual=evt.actual,
                forecast=evt.forecast,
                previous=evt.previous,
                unit=evt.unit,
                category=evt.category,
                impact=evt.impact,
                url=evt.url,
            )
        )

    return EconomicEventListResponse(
        events=events,
        total=result.total,
        from_date=result.from_date,
        to_date=result.to_date,
        country_filter=result.country_filter,
        volatility_filter=result.volatility_filter,
    )


@router.get("/countries", response_model=EconomicCalendarCountriesResponse)
async def get_economic_countries() -> EconomicCalendarCountriesResponse:
    """List supported countries for filtering economic events."""
    countries = await EconomicCalendarService.list_countries()

    return EconomicCalendarCountriesResponse(
        countries=[CountryInfo(code=c["code"], name=c["name"]) for c in countries],
        total=len(countries),
    )
