from backend.app.agents.supervisor import run_trip
from backend.app.schemas.itinerary import TripPlan
from backend.app.schemas.trip import TripRequest


async def generate_trip_plan(trip: TripRequest) -> TripPlan:
    return await run_trip(trip)