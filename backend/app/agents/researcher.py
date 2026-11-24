from backend.app.schemas.itinerary import TravelContext
from backend.app.schemas.trip import TripRequest
from backend.app.services.travel_context import collect_travel_context


async def research_trip(trip: TripRequest) -> TravelContext:
    return await collect_travel_context(trip)