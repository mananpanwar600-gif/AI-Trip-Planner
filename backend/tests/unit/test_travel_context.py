import asyncio
from datetime import date, timedelta

from backend.app.schemas.context import Coordinates
from backend.app.schemas.itinerary import ContextFact
from backend.app.schemas.trip import TripRequest
from backend.app.services import travel_context
from backend.app.utils.exceptions import TravelProviderError


def test_context_collects_weather_and_surfaces_optional_provider_failures(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("EXCHANGE_RATE_API_KEY", "")
    async def geocode(_query):
        return Coordinates(
            name="Kyoto",
            country="Japan",
            latitude=35.0,
            longitude=135.0,
        )

    async def places(_location):
        raise TravelProviderError("Geoapify", "GEOAPIFY_API_KEY is missing.")

    async def weather(_location, _days):
        return [
            ContextFact(
                source="Open-Meteo forecast",
                detail="2025-01-01: Clear.",
            )
        ]

    async def wikipedia(_destination):
        return ["Wikipedia: local history"]

    async def wikidata(_destination):
        return []

    monkeypatch.setattr(travel_context, "geocode_city", geocode)
    monkeypatch.setattr(travel_context, "get_weather_facts", weather)
    monkeypatch.setattr(travel_context, "get_nearby_places", places)
    monkeypatch.setattr(travel_context, "search_wikipedia", wikipedia)
    monkeypatch.setattr(travel_context, "search_wikidata", wikidata)

    result = asyncio.run(
        travel_context.collect_travel_context(TripRequest(destination="Kyoto"))
    )

    assert any("Open-Meteo forecast" == fact.source for fact in result.facts)
    assert any("Wikipedia" in fact.detail for fact in result.facts)
    assert result.warnings == ["GEOAPIFY_API_KEY is missing."]


def test_context_limits_date_weather_to_forecast_horizon(monkeypatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("EXCHANGE_RATE_API_KEY", "")
    start_date = date.today() + timedelta(days=13)
    end_date = date.today() + timedelta(days=18)
    weather_dates = []

    async def geocode(_query):
        return Coordinates(
            name="Kyoto",
            country="Japan",
            latitude=35.0,
            longitude=135.0,
        )

    async def weather(_location, _days, *, start_date, end_date):
        weather_dates.append((start_date, end_date))
        return []

    async def no_places(_location):
        return []

    async def no_accommodation(_location):
        return []

    async def no_research(_destination):
        return []

    monkeypatch.setattr(travel_context, "geocode_city", geocode)
    monkeypatch.setattr(travel_context, "get_weather_facts", weather)
    monkeypatch.setattr(travel_context, "get_nearby_places", no_places)
    monkeypatch.setattr(
        travel_context, "find_accommodation_facts", no_accommodation
    )
    monkeypatch.setattr(travel_context, "search_wikipedia", no_research)
    monkeypatch.setattr(travel_context, "search_wikidata", no_research)

    result = asyncio.run(
        travel_context.collect_travel_context(
            TripRequest(
                destination="Kyoto",
                start_date=start_date,
                end_date=end_date,
            )
        )
    )

    assert weather_dates == [
        (start_date, date.today() + timedelta(days=15))
    ]
    assert any("cannot cover every selected trip date" in item for item in result.warnings)


def test_context_uses_geocoded_indian_state_for_research(monkeypatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setenv("EXCHANGE_RATE_API_KEY", "")
    wikipedia_queries = []
    guide_locations = []

    async def geocode(_query):
        return Coordinates(
            name="Jaipur",
            region="Rajasthan",
            country="India",
            country_code="IN",
            latitude=26.9,
            longitude=75.8,
        )

    async def no_weather(_location, _days):
        return []

    async def no_places(_location):
        return []

    async def no_accommodation(_location):
        return []

    async def wikipedia(query):
        wikipedia_queries.append(query)
        return []

    async def no_wikidata(_destination):
        return []

    async def guide(_trip, *, region, country, country_code):
        guide_locations.append((region, country, country_code))
        return []

    async def no_prices(_trip, **_location):
        return []

    monkeypatch.setattr(travel_context, "geocode_city", geocode)
    monkeypatch.setattr(travel_context, "get_weather_facts", no_weather)
    monkeypatch.setattr(travel_context, "get_nearby_places", no_places)
    monkeypatch.setattr(
        travel_context, "find_accommodation_facts", no_accommodation
    )
    monkeypatch.setattr(travel_context, "search_wikipedia", wikipedia)
    monkeypatch.setattr(travel_context, "search_wikidata", no_wikidata)
    monkeypatch.setattr(travel_context, "search_destination_guide", guide)
    monkeypatch.setattr(travel_context, "search_destination_prices", no_prices)
    monkeypatch.setattr(travel_context, "search_visa_prices", no_prices)

    result = asyncio.run(
        travel_context.collect_travel_context(
            TripRequest(destination="Jaipur", currency="INR")
        )
    )

    location = next(fact for fact in result.facts if fact.source == "Location")
    assert "State/region: Rajasthan" in location.detail
    assert "Country code: IN" in location.detail
    assert wikipedia_queries == ["Jaipur, Rajasthan, India"]
    assert guide_locations == [("Rajasthan", "India", "IN")]
