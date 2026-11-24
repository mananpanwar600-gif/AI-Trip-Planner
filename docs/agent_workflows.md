# Agent workflow

The Streamlit app and FastAPI endpoints use the same LangGraph workflow.
Specialist agents share a typed trip state and run in this order:

- **Supervisor:** checks the request and verifies that Groq is configured.
- **Researcher:** resolves the destination, then gathers forecast, nearby
  places/accommodation, and reference facts. It also estimates a driving route
  when the user supplies an origin. Independent research providers run
  concurrently inside this agent.
- **Planner:** uses a LangChain chat prompt template to request a personalized
  JSON itinerary from the configured Groq model. Planner tokens can stream to
  the UI/API while the graph runs.
- **Budget reviewer:** checks the estimate and unpriced categories against the
  requested budget, adding explicit warnings to the plan.
- **Validator:** verifies that itinerary days are sequential before the graph
  returns a plan.

If a research provider is unavailable, the itinerary can still be generated and
the unavailable source is named in the returned `travel_context.warnings`.
