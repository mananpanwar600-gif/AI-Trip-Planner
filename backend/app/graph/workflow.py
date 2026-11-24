from langgraph.graph import END, START, StateGraph

from backend.app.graph.edges import has_research_context
from backend.app.graph.nodes import (
    budget_node,
    planner_node,
    research_node,
    supervisor_node,
    validator_node,
)
from backend.app.graph.state import TokenCallback, TripState
from backend.app.schemas.trip import TripRequest


def _build_trip_graph():
    graph = StateGraph(TripState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("researcher", research_node)
    graph.add_node("planner", planner_node)
    graph.add_node("budget_reviewer", budget_node)
    graph.add_node("validator", validator_node)

    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "researcher")
    graph.add_conditional_edges(
        "researcher",
        lambda state: "planner" if has_research_context(state) else END,
        {"planner": "planner", END: END},
    )
    graph.add_edge("planner", "budget_reviewer")
    graph.add_edge("budget_reviewer", "validator")
    graph.add_edge("validator", END)
    return graph.compile()


trip_graph = _build_trip_graph()


async def run_trip_workflow(
    trip: TripRequest,
    on_token: TokenCallback | None = None,
) -> TripState:
    initial_state: TripState = {"request": trip, "on_token": on_token}
    state = await trip_graph.ainvoke(initial_state)
    if not has_research_context(state):
        raise RuntimeError("Trip workflow could not collect research context.")
    return state