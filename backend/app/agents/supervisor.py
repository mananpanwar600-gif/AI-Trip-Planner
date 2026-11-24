from backend.app.config import get_settings
from backend.app.graph.workflow import run_trip_workflow
from backend.app.schemas.itinerary import TripPlan
from backend.app.schemas.trip import TripRequest
from backend.app.services.groq import GroqServiceError


async def run_trip(trip: TripRequest) -> TripPlan:
    if not get_settings().groq_api_key:
        raise GroqServiceError(
            "GROQ_API_KEY is not configured. Add it to your local .env file.",
            status_code=503,
        )
    state = await run_trip_workflow(trip)
    plan = state.get("plan")
    if plan is None:
        raise RuntimeError("Trip workflow finished without an itinerary.")
    return plan