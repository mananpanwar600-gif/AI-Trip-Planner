from backend.app.agents.planner import plan_trip
from backend.app.agents.researcher import research_trip
from backend.app.graph.state import TripState


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
    return {"plan": await plan_trip(request, context)}