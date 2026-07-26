"""Mock Economic Calendar provider — deterministic, no network.

Used in automated tests and as the automatic fallback when
ECONOMIC_CALENDAR_API_KEY is not configured.  Returns a small but
realistic set of synthetic economic events.

All events are generated from a fixed seed so tests can assert exact
values.  Dates are anchored relative to ``now`` so they remain in the
future regardless of when the test runs.
"""
from datetime import datetime, timedelta, timezone
from providers.economic_calendar.base import (
    EconomicCalendarProvider,
    EconomicEvent,
    EconomicEventList,
    Volatility,
)


# ── Synthetic data ────────────────────────────────────────────────

_SAMPLE_EVENTS: list[dict] = [
    {
        "id": "mock-nfp",
        "name": "Non-Farm Payrolls",
        "country_code": "US",
        "country_name": "United States",
        "currency": "USD",
        "volatility": Volatility.HIGH,
        "actual": "216K",
        "forecast": "200K",
        "previous": "199K",
        "unit": "Jobs",
        "category": "Employment",
        "offset_hours": 8,
    },
    {
        "id": "mock-cpi-us",
        "name": "Consumer Price Index (YoY)",
        "country_code": "US",
        "country_name": "United States",
        "currency": "USD",
        "volatility": Volatility.HIGH,
        "actual": "3.2%",
        "forecast": "3.3%",
        "previous": "3.4%",
        "unit": "Percent",
        "category": "Inflation",
        "offset_hours": 24,
    },
    {
        "id": "mock-gdp-eu",
        "name": "GDP Growth Rate (QoQ)",
        "country_code": "EU",
        "country_name": "Eurozone",
        "currency": "EUR",
        "volatility": Volatility.HIGH,
        "actual": "0.2%",
        "forecast": "0.3%",
        "previous": "0.1%",
        "unit": "Percent",
        "category": "GDP",
        "offset_hours": 32,
    },
    {
        "id": "mock-pmi-br",
        "name": "Manufacturing PMI",
        "country_code": "BR",
        "country_name": "Brazil",
        "currency": "BRL",
        "volatility": Volatility.MEDIUM,
        "actual": None,
        "forecast": "52.1",
        "previous": "51.8",
        "unit": "Index",
        "category": "Activity",
        "offset_hours": 48,
    },
    {
        "id": "mock-bank-eng",
        "name": "Bank of England Interest Rate Decision",
        "country_code": "GB",
        "country_name": "United Kingdom",
        "currency": "GBP",
        "volatility": Volatility.HIGH,
        "actual": None,
        "forecast": "5.00%",
        "previous": "5.25%",
        "unit": "Percent",
        "category": "Central Bank",
        "offset_hours": 72,
    },
    {
        "id": "mock-unemp-jp",
        "name": "Unemployment Rate",
        "country_code": "JP",
        "country_name": "Japan",
        "currency": "JPY",
        "volatility": Volatility.LOW,
        "actual": "2.5%",
        "forecast": "2.6%",
        "previous": "2.6%",
        "unit": "Percent",
        "category": "Employment",
        "offset_hours": 96,
    },
    {
        "id": "mock-retail-de",
        "name": "Retail Sales (MoM)",
        "country_code": "DE",
        "country_name": "Germany",
        "currency": "EUR",
        "volatility": Volatility.LOW,
        "actual": None,
        "forecast": "0.5%",
        "previous": "-0.2%",
        "unit": "Percent",
        "category": "Activity",
        "offset_hours": 120,
    },
    {
        "id": "mock-trade-cn",
        "name": "Trade Balance",
        "country_code": "CN",
        "country_name": "China",
        "currency": "CNY",
        "volatility": Volatility.MEDIUM,
        "actual": "82.3B",
        "forecast": "80.0B",
        "previous": "81.7B",
        "unit": "USD",
        "category": "Trade",
        "offset_hours": 144,
    },
    {
        "id": "mock-fomc",
        "name": "FOMC Meeting Minutes",
        "country_code": "US",
        "country_name": "United States",
        "currency": "USD",
        "volatility": Volatility.HIGH,
        "actual": None,
        "forecast": None,
        "previous": None,
        "unit": None,
        "category": "Central Bank",
        "offset_hours": 168,
    },
]


class MockEconomicCalendarProvider(EconomicCalendarProvider):
    name = "mock"

    async def list_events(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        country_code: str | None = None,
        volatility: Volatility | str | None = None,
        limit: int = 100,
    ) -> EconomicEventList:
        now = datetime.now(timezone.utc)

        events = []
        for raw in _SAMPLE_EVENTS:
            dt = now + timedelta(hours=raw["offset_hours"])
            event = EconomicEvent(
                id=raw["id"],
                name=raw["name"],
                country_code=raw["country_code"],
                country_name=raw["country_name"],
                currency=raw["currency"],
                date_utc=dt,
                volatility=raw["volatility"],
                actual=raw.get("actual"),
                forecast=raw.get("forecast"),
                previous=raw.get("previous"),
                unit=raw.get("unit"),
                category=raw.get("category"),
            )
            events.append(event)

        # Filter by date range
        if start_date:
            events = [e for e in events if e.date_utc >= start_date]
        if end_date:
            events = [e for e in events if e.date_utc <= end_date]

        # Filter by country
        if country_code:
            events = [e for e in events if e.country_code == country_code.upper()]

        # Filter by volatility
        if volatility:
            v = volatility.value if isinstance(volatility, Volatility) else volatility
            threshold = Volatility(v.upper())
            order = [Volatility.NONE, Volatility.LOW, Volatility.MEDIUM, Volatility.HIGH]
            min_idx = order.index(threshold)
            events = [e for e in events if order.index(e.volatility) >= min_idx]

        # Apply limit
        events = events[:limit]

        return EconomicEventList(
            events=events,
            total=len(events),
            from_date=(start_date or now).strftime("%Y-%m-%d"),
            to_date=(end_date or now + timedelta(days=7)).strftime("%Y-%m-%d"),
            country_filter=country_code.upper() if country_code else None,
            volatility_filter=volatility.value if isinstance(volatility, Volatility) else volatility,
        )

    async def list_countries(self) -> list[dict[str, str]]:
        return [
            {"code": "US", "name": "United States"},
            {"code": "EU", "name": "Eurozone"},
            {"code": "BR", "name": "Brazil"},
            {"code": "GB", "name": "United Kingdom"},
            {"code": "JP", "name": "Japan"},
            {"code": "DE", "name": "Germany"},
            {"code": "CN", "name": "China"},
        ]
