# Agent workflow

The current planner keeps the interface simple while using a small backend
workflow:

- **Supervisor:** verifies that Groq is configured and starts the workflow.
- **Researcher:** resolves the destination, then gathers forecast, nearby
  places/accommodation, and reference facts. It also estimates a driving route
  when the user supplies an origin.
- **Planner:** requests a personalized JSON itinerary from the configured Groq
  model using trip details and available research.
- **Validator:** checks that itinerary days are sequential and warns when the
  model's estimated total exceeds the requested budget or is below the listed
  activity subtotal.

The independent research providers run concurrently. If one is unavailable,
the itinerary can still be generated and the unavailable source is named in
the returned `travel_context.warnings`.