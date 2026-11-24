from backend.app.graph.state import TokenCallback
from backend.app.graph.workflow import run_trip_workflow
from backend.app.schemas.itinerary import TripPlan
from backend.app.schemas.trip import TripRequest


async def run_trip(
    trip: TripRequest,
    on_token: TokenCallback | None = None,
) -> TripPlan:
    state = await run_trip_workflow(trip, on_token=on_token)
    plan = state.get("plan")
    if plan is None:
        raise RuntimeError("Trip workflow finished without an itinerary.")
    return plan