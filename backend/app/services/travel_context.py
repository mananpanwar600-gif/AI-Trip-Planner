import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import date, timedelta

from backend.app.agents.accommodation import find_accommodation_facts
from backend.app.agents.transport import get_route_fact
from backend.app.agents.weather import get_weather_facts
from backend.app.config import get_settings
from backend.app.schemas.context import Coordinates
from backend.app.schemas.itinerary import ContextFact, TravelContext
from backend.app.schemas.trip import TripRequest
from backend.app.tools.currency import get_rates_to_target
from backend.app.tools.geocoding import geocode_city
from backend.app.tools.places import get_nearby_places
from backend.app.tools.tavily import (
    search_destination_guide,
    search_destination_prices,
    search_flight_prices,
    search_visa_prices,
)
from backend.app.tools.web_research import search_wikidata, search_wikipedia
from backend.app.utils.exceptions import TravelProviderError

logger = logging.getLogger(__name__)


async def collect_travel_context(trip: TripRequest) -> TravelContext:
    facts: list[ContextFact] = []
    warnings: list[str] = []
    destination: Coordinates | None = None
    destination_query = trip.destination
    lookups: list[tuple[str, Callable[[], Awaitable[list[ContextFact]]]]] = []
    settings = get_settings()
    exchange_rate_task = (
        asyncio.create_task(get_rates_to_target(trip.currency))
        if settings.exchange_rate_api_key
        else None
    )

    try:
        destination = await geocode_city(trip.destination)
        destination_parts = [destination.name]
        for location_part in (destination.region, destination.country):
            if (
                location_part
                and location_part.casefold()
                not in ", ".join(destination_parts).casefold()
            ):
                destination_parts.append(location_part)
        destination_query = ", ".join(destination_parts)
        location_parts = [f"Place: {destination.name}"]
        if destination.region:
            location_parts.append(f"State/region: {destination.region}")
        if destination.country:
            location_parts.append(f"Country: {destination.country}")
        if destination.country_code:
            location_parts.append(f"Country code: {destination.country_code}")
        facts.append(
            ContextFact(source="Location", detail="; ".join(location_parts))
        )
    except TravelProviderError as exc:
        warnings.append(str(exc))
        logger.info("Destination lookup unavailable: %s", exc.provider)

    if destination:
        async def place_facts() -> list[ContextFact]:
            places = await get_nearby_places(destination)
            return [
                ContextFact(
                    source="Geoapify",
                    detail=f"{place.name} — {place.address}",
                )
                for place in places
            ]

        async def accommodation_facts() -> list[ContextFact]:
            return await find_accommodation_facts(destination)

        async def wikipedia_facts() -> list[ContextFact]:
            research = await search_wikipedia(destination_query)
            return [
                ContextFact(source="Destination research", detail=fact)
                for fact in research
            ]

        async def wikidata_facts() -> list[ContextFact]:
            research = await search_wikidata(trip.destination)
            return [
                ContextFact(source="Destination research", detail=fact)
                for fact in research
            ]

        lookups.extend(
            [
                ("nearby places", place_facts),
                ("accommodation", accommodation_facts),
                ("Wikipedia research", wikipedia_facts),
                ("Wikidata research", wikidata_facts),
            ]
        )
        if trip.start_date is None or trip.end_date is None:
            if trip.trip_days > 16:
                warnings.append(
                    "Open-Meteo forecasts are available for the first 16 trip days only."
                )
            lookups.insert(
                0,
                ("weather", lambda: get_weather_facts(destination, trip.trip_days)),
            )
        else:
            today = date.today()
            last_forecast_date = today + timedelta(days=15)
            forecast_start = max(trip.start_date, today)
            forecast_end = min(trip.end_date, last_forecast_date)
            if forecast_start > trip.start_date or forecast_end < trip.end_date:
                warnings.append(
                    "Open-Meteo's 16-day forecast cannot cover every selected trip "
                    f"date (available from {today.isoformat()} through "
                    f"{last_forecast_date.isoformat()}). Check the weather closer "
                    "to departure."
                )
            if forecast_start <= forecast_end:
                forecast_days = (forecast_end - forecast_start).days + 1
                lookups.insert(
                    0,
                    (
                        "weather",
                        lambda: get_weather_facts(
                            destination,
                            forecast_days,
                            start_date=forecast_start,
                            end_date=forecast_end,
                        ),
                    ),
                )
    if settings.tavily_api_key:
        if destination:
            lookups.append(
                (
                    "destination guide research",
                    lambda: search_destination_guide(
                        trip,
                        region=destination.region,
                        country=destination.country,
                        country_code=destination.country_code,
                    ),
                )
            )
        lookups.append(
            (
                "destination price research",
                lambda: search_destination_prices(
                    trip,
                    region=destination.region if destination else None,
                    country=destination.country if destination else None,
                ),
            )
        )
        lookups.append(
            (
                "visa price research",
                lambda: search_visa_prices(
                    trip,
                    region=destination.region if destination else None,
                    country=destination.country if destination else None,
                ),
            )
        )
        if trip.origin:
            lookups.append(
                (
                    "flight price research",
                    lambda: search_flight_prices(
                        trip,
                        region=destination.region if destination else None,
                        country=destination.country if destination else None,
                    ),
                )
            )

    if lookups:
        results = await asyncio.gather(
            *(_capture(name, lookup) for name, lookup in lookups)
        )
        for result_facts, warning in results:
            facts.extend(result_facts)
            if warning:
                warnings.append(warning)

    if trip.origin and destination:
        try:
            origin = await geocode_city(trip.origin)
            facts.append(await get_route_fact(origin, destination))
        except TravelProviderError as exc:
            warnings.append(str(exc))
            logger.info("Route lookup unavailable: %s", exc.provider)

    exchange_rates: dict[str, float] = {}
    exchange_rate_updated_at = None
    if exchange_rate_task is not None:
        try:
            exchange_rates, exchange_rate_updated_at = await exchange_rate_task
        except TravelProviderError as exc:
            warnings.append(str(exc))
            logger.info("Currency conversion lookup unavailable: %s", exc.provider)

    return TravelContext(
        facts=facts[:40],
        warnings=warnings[:10],
        exchange_rates=exchange_rates,
        exchange_rate_updated_at=exchange_rate_updated_at,
    )


async def _capture(
    name: str,
    lookup: Callable[[], Awaitable[list[ContextFact]]],
) -> tuple[list[ContextFact], str | None]:
    try:
        return await lookup(), None
    except TravelProviderError as exc:
        logger.info("%s lookup unavailable: %s", name, exc.provider)
        return [], str(exc)


