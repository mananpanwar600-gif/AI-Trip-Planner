from backend.app.agents.validator import validate_plan
from backend.app.schemas.itinerary import TravelContext, TripPlan
from backend.app.schemas.trip import TripRequest
from backend.app.services.groq import TokenCallback, generate_trip_plan


async def plan_trip(
    trip: TripRequest,
    context: TravelContext,
    on_token: TokenCallback | None = None,
) -> TripPlan:
    plan = await generate_trip_plan(trip, context=context, on_token=on_token)
    return validate_plan(trip, plan)