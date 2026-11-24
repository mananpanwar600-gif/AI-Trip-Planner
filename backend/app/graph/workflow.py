from backend.app.graph.edges import has_research_context
from backend.app.graph.nodes import planner_node, research_node
from backend.app.graph.state import TripState
from backend.app.schemas.trip import TripRequest


async def run_trip_workflow(trip: TripRequest) -> TripState:
    state: TripState = {"request": trip}
    state.update(await research_node(state))
    if not has_research_context(state):
        raise RuntimeError("Trip workflow could not collect research context.")
    state.update(await planner_node(state))
    return state