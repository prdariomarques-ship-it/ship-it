"""RapidAPI Economic Calendar provider.

Calls https://economic-calendar-api.p.rapidapi.com to fetch structured
macroeconomic events.  The RapidAPI key is read from the environment
variable ECONOMIC_CALENDAR_API_KEY via the existing Settings class.

Docs: https://docs.fxstreet.com/api/calendar/  (conceptually similar)
      https://rapidapi.com/yasimpratama88/api/economic-calendar-api
"""
from datetime import datetime, timezone
import httpx
from providers.economic_calendar.base import (
    EconomicCalendarProvider,
    EconomicCalendarProviderError,
    EconomicEvent,
    EconomicEventList,
    Volatility,
)
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://economic-calendar-api.p.rapidapi.com"
_TIMEOUT = 30.0


class RapidAPIEconomicCalendarProvider(EconomicCalendarProvider):
    name = "rapidapi"

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.economic_calendar_api_key
        if not self._api_key:
            raise EconomicCalendarProviderError(
                "ECONOMIC_CALENDAR_API_KEY is not set. "
                "Set it in your environment or .env file to use the "
                "RapidAPI provider."
            )
        self._headers = {
            "X-RapidAPI-Key": self._api_key,
            "X-RapidAPI-Host": "economic-calendar-api.p.rapidapi.com",
        }

    async def list_events(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        country_code: str | None = None,
        volatility: Volatility | str | None = None,
        limit: int = 100,
    ) -> EconomicEventList:
        params: dict[str, str] = {}

        # Date range
        if start_date:
            params["startDate"] = start_date.strftime("%Y-%m-%d")
        else:
            params["startDate"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if end_date:
            params["endDate"] = end_date.strftime("%Y-%m-%d")
        else:
            end = datetime.now(timezone.utc)
            from datetime import timedelta
            params["endDate"] = (end + timedelta(days=7)).strftime("%Y-%m-%d")

        if country_code:
            params["countryCode"] = country_code.upper()

        if volatility:
            v = volatility.value if isinstance(volatility, Volatility) else volatility
            params["volatility"] = v.upper()

        params["limit"] = str(min(limit, 500))  # API max is 500
        params["timezone"] = "GMT+0"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"{_BASE_URL}/calendar",
                    headers=self._headers,
                    params=params,
                )
                resp.raise_for_status()
                raw = resp.json()
        except httpx.HTTPError as exc:
            logger.error("RapidAPI economic calendar request failed: %s", exc)
            raise EconomicCalendarProviderError(str(exc)) from exc

        events = []
        for item in raw:
            try:
                evt = EconomicEvent(
                    id=str(item.get("id", "")),
                    name=item.get("name", "Unknown Event"),
                    country_code=item.get("countryCode", ""),
                    country_name=item.get("countryName", item.get("countryCode", "")),
                    currency=item.get("currencyCode", ""),
                    date_utc=_parse_utc(item.get("dateUtc", "")),
                    volatility=Volatility(
                        (item.get("volatility", "NONE") or "NONE").upper()
                    ),
                    actual=item.get("actual"),
                    forecast=item.get("consensus"),
                    previous=item.get("previous"),
                    unit=item.get("unit"),
                    category=item.get("category"),
                    impact=item.get("impact"),
                    url=item.get("url"),
                )
                events.append(evt)
            except (ValueError, KeyError) as exc:
                logger.warning("Skipping malformed event record: %s", exc)
                continue

        return EconomicEventList(
            events=events,
            total=len(events),
            from_date=params.get("startDate"),
            to_date=params.get("endDate"),
            country_filter=params.get("countryCode"),
            volatility_filter=params.get("volatility"),
        )

    async def list_countries(self) -> list[dict[str, str]]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"{_BASE_URL}/country",
                    headers=self._headers,
                )
                resp.raise_for_status()
                raw = resp.json()
        except httpx.HTTPError as exc:
            logger.error("RapidAPI country list request failed: %s", exc)
            raise EconomicCalendarProviderError(str(exc)) from exc

        return [
            {
                "code": item.get("countryCode", ""),
                "name": item.get("countryName", item.get("countryCode", "")),
            }
            for item in raw
            if item.get("countryCode")
        ]


def _parse_utc(value: str) -> datetime:
    """Parse a UTC timestamp string into a timezone-aware datetime."""
    if not value:
        return datetime.now(timezone.utc)
    # Handle common ISO formats
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    # Fallback
    return datetime.now(timezone.utc)
