import logging

import httpx

from backend.app.config import get_settings
from backend.app.schemas.itinerary import ContextFact
from backend.app.schemas.trip import TripRequest
from backend.app.utils.exceptions import TravelProviderError

logger = logging.getLogger(__name__)
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


async def search_destination_prices(
    trip: TripRequest,
    *,
    region: str | None = None,
    country: str | None = None,
) -> list[ContextFact]:
    nights = max(trip.trip_days - 1, 0)
    destination = _qualified_destination(trip.destination, region, country)
    query = (
        f"{trip.travel_style} travel budget prices for lodging, meals, local "
        f"transport, and travel insurance in {destination}; {trip.trip_days} "
        f"days and {nights} nights for {trip.travelers} travelers; "
        f"prices in {trip.currency}; current traveler cost guide"
    )
    return await _search_results(query, "Tavily destination cost research")


async def search_destination_guide(
    trip: TripRequest,
    *,
    region: str | None,
    country: str | None,
    country_code: str | None,
) -> list[ContextFact]:
    place = _qualified_destination(trip.destination, region, country)
    if country_code == "IN":
        query = (
            f"State- or union-territory-specific official tourism and travel guide "
            f"for {place}; major attractions, regional food, local transport, "
            "practical travel advice, and realistic distances. Do not mix in "
            "unrelated Indian states."
        )
    else:
        query = (
            f"Official tourism and destination guide for {place}; major nearby "
            "attractions, local food, transport, practical visitor advice, and "
            "realistic distances."
        )
    return await _search_results(
        query,
        "Tavily destination guide",
        max_results=3,
        content_limit=900,
    )


async def search_visa_prices(
    trip: TripRequest,
    *,
    region: str | None = None,
    country: str | None = None,
) -> list[ContextFact]:
    destination = _qualified_destination(trip.destination, region, country)
    query = (
        f"official tourist visa application fees for visiting {destination}; "
        f"visitor visa fee amounts in {trip.currency}"
    )
    return await _search_results(query, "Tavily visa price search")


async def search_flight_prices(
    trip: TripRequest,
    *,
    region: str | None = None,
    country: str | None = None,
) -> list[ContextFact]:
    if not trip.origin:
        return []
    destination = _qualified_destination(trip.destination, region, country)
    date_text = (
        f"from {trip.start_date.isoformat()} through {trip.end_date.isoformat()}"
        if trip.start_date and trip.end_date
        else f"for a {trip.trip_days}-day trip"
    )
    query = (
        f"round-trip economy flight price from {trip.origin} to {destination} "
        f"{date_text} for {trip.travelers} travelers; price in {trip.currency}"
    )
    return await _search_results(query, "Tavily flight price search")


def _qualified_destination(
    destination: str,
    region: str | None,
    country: str | None,
) -> str:
    parts = [destination]
    included = destination.casefold()
    for location_part in (region, country):
        if location_part and location_part.casefold() not in included:
            parts.append(location_part)
            included += f", {location_part.casefold()}"
    return ", ".join(parts)


async def _search_results(
    query: str,
    source: str,
    *,
    max_results: int = 5,
    content_limit: int = 1_800,
) -> list[ContextFact]:
    api_key = get_settings().tavily_api_key
    if not api_key:
        raise TravelProviderError(
            "Tavily", "TAVILY_API_KEY is not configured; price research was skipped."
        )

    try:
        async with httpx.AsyncClient(
            timeout=get_settings().external_api_timeout
        ) as client:
            response = await client.post(
                TAVILY_SEARCH_URL,
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise TravelProviderError("Tavily", "Tavily price research timed out.") from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("Tavily returned HTTP %s.", exc.response.status_code)
        raise TravelProviderError(
            "Tavily", "Tavily price research is temporarily unavailable."
        ) from exc
    except httpx.RequestError as exc:
        logger.warning("Tavily request failed (%s).", exc.__class__.__name__)
        raise TravelProviderError(
            "Tavily", "Could not connect to Tavily price research."
        ) from exc
    except (ValueError, TypeError) as exc:
        raise TravelProviderError(
            "Tavily", "Tavily returned an invalid price response."
        ) from exc

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise TravelProviderError("Tavily", "Tavily returned invalid search results.")

    facts = []
    for result in results:
        if not isinstance(result, dict):
            continue
        title = result.get("title")
        url = result.get("url")
        content = result.get("content")
        if not all(isinstance(value, str) and value.strip() for value in (title, url, content)):
            continue
        facts.append(
            ContextFact(
                source=source,
                title=title.strip(),
                detail=content.strip()[:content_limit],
                url=url.strip(),
            )
        )
    if not facts:
        raise TravelProviderError(
            "Tavily", "No usable linked results were found for this search."
        )
    return facts
