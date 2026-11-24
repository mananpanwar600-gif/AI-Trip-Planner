from backend.app.graph.state import TripState


def has_research_context(state: TripState) -> bool:
    return state.get("context") is not None