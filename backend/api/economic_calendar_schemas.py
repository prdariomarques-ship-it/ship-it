"""API schemas for the Economic Calendar endpoints."""
from pydantic import BaseModel, Field
from providers.economic_calendar.base import Volatility


class EconomicEventResponse(BaseModel):
    id: str
    name: str
    country_code: str
    country_name: str
    currency: str
    date_utc: str
    volatility: str
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None
    unit: str | None = None
    category: str | None = None
    impact: str | None = None
    url: str | None = None


class EconomicEventListResponse(BaseModel):
    events: list[EconomicEventResponse]
    total: int
    from_date: str | None = None
    to_date: str | None = None
    country_filter: str | None = None
    volatility_filter: str | None = None


class CountryInfo(BaseModel):
    code: str
    name: str


class EconomicCalendarCountriesResponse(BaseModel):
    countries: list[CountryInfo]
    total: int
