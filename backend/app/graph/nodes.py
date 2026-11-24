from backend.app.agents.budget import review_budget
from backend.app.agents.planner import draft_trip
from backend.app.agents.researcher import research_trip
from backend.app.agents.validator import validate_plan_shape
from backend.app.config import get_settings
from backend.app.graph.state import TripState
from backend.app.services.groq import GroqServiceError


def supervisor_node(state: TripState) -> TripState:
    if state.get("request") is None:
        raise RuntimeError("Trip workflow is missing its request.")
    if not get_settings().groq_api_key:
        raise GroqServiceError(
            "GROQ_API_KEY is not configured. Add it to your local .env file.",
            status_code=503,
        )
    return {}


async def research_node(state: TripState) -> TripState:
    request = state.get("request")
    if request is None:
        raise RuntimeError("Trip workflow is missing its request.")
    return {"context": await research_trip(request)}


async def planner_node(state: TripState) -> TripState:
    request = state.get("request")
    context = state.get("context")
    if request is None or context is None:
        raise RuntimeError("Trip workflow is missing research context.")
    return {
        "plan": await draft_trip(
            request,
            context,
            on_token=state.get("on_token"),
        )
    }


def budget_node(state: TripState) -> TripState:
    request = state.get("request")
    plan = state.get("plan")
    if request is None or plan is None:
        raise RuntimeError("Trip workflow is missing the itinerary for budget review.")

    reviewed_plan = plan.model_copy(deep=True)
    reviewed_plan.travel_context.warnings.extend(review_budget(request, reviewed_plan))
    reviewed_plan.travel_context.warnings = reviewed_plan.travel_context.warnings[-10:]
    return {"plan": reviewed_plan}


def validator_node(state: TripState) -> TripState:
    request = state.get("request")
    plan = state.get("plan")
    if request is None or plan is None:
        raise RuntimeError("Trip workflow is missing the itinerary for validation.")
    return {"plan": validate_plan_shape(request, plan)}