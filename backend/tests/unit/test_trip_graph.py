import asyncio

from backend.app.graph import nodes, workflow
from backend.app.schemas.itinerary import TravelContext, TripPlan
from backend.app.schemas.trip import TripRequest


def test_langgraph_runs_specialist_agents_and_streams_planner_tokens(
    monkeypatch,
) -> None:
    trip = TripRequest(destination="Kyoto", trip_days=1, budget=50)
    streamed_tokens = []

    async def fake_research(_trip):
        return TravelContext()

    async def fake_draft(_trip, context, on_token=None):
        assert context == TravelContext()
        assert on_token is not None
        await on_token("drafting")
        return TripPlan(
            destination="Kyoto",
            overview="A relaxed trip.",
            days=[
                {
                    "day": 1,
                    "title": "Explore",
                    "activities": [
                        {
                            "time": "09:00",
                            "name": "Visit a garden",
                            "description": "Take a walk.",
                            "location": "Kyoto",
                            "estimated_cost": 10,
                        }
                    ],
                }
            ],
            estimated_total_cost=75,
        )

    async def capture_token(token):
        streamed_tokens.append(token)

    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setattr(nodes, "research_trip", fake_research)
    monkeypatch.setattr(nodes, "draft_trip", fake_draft)
    monkeypatch.setattr(workflow, "trip_graph", workflow._build_trip_graph())

    state = asyncio.run(
        workflow.run_trip_workflow(trip, on_token=capture_token)
    )

    assert streamed_tokens == ["drafting"]
    assert state["context"] == TravelContext()
    assert [day.day for day in state["plan"].days] == [1]
    assert any(
        "above your 50 USD budget" in warning
        for warning in state["plan"].travel_context.warnings
    )
    assert {
        "supervisor",
        "researcher",
        "planner",
        "budget_reviewer",
        "validator",
    }.issubset(workflow.trip_graph.get_graph().nodes)
