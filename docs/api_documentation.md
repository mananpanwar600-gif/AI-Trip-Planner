# API

The user interface is Streamlit. The optional FastAPI service is available for
other clients. Interactive Swagger documentation is available at `/docs`.

## `GET /api/health`

Returns application status and whether optional/required providers are
configured. It does not expose credentials or make upstream requests.

## `POST /api/trips/plan`

Example request:

```json
{
  "destination": "Kyoto, Japan",
  "origin": "Tokyo, Japan",
  "trip_days": 3,
  "start_date": "2026-12-01",
  "end_date": "2026-12-03",
  "travelers": 2,
  "budget": 900,
  "currency": "USD",
  "interests": ["food", "gardens"],
  "pace": "relaxed",
  "additional_preferences": "Vegetarian meals; avoid long walks."
}
```

`destination` is required. `trip_days` is 1–21, `travelers` is 1–20, and
`budget` is optional and positive. `currency` is a three-letter uppercase code.
`start_date` and `end_date` are optional ISO dates; provide both to set the
inclusive travel period, which determines `trip_days`. Date ranges may be at
most 21 days.
`pace` can be `relaxed`, `balanced`, or `active`; `additional_preferences` is
an optional note of up to 500 characters.

The response contains the destination, overview, estimated total, daily
activities, practical tips, an itemized `budget_breakdown`, and `travel_context`
(facts, optional source titles/URLs, and provider warnings). The response
includes a `trip_id`; plans and their input are stored in the configured local
SQLite database. Prices with a known source currency are converted to the
requested currency when `EXCHANGE_RATE_API_KEY` is configured. Prices without a
source currency or available conversion rate are excluded and identified in
`budget_breakdown.unpriced_categories` and `travel_context.warnings`.
Flight, visa, and destination price ranges are sourced estimates, not live
bookable quotes; generic visa estimates may not apply to every passport.

## Streaming itinerary generation

`POST /api/trips/plan/stream` accepts the same JSON body as `/api/trips/plan`
and returns a Server-Sent Events stream. Events are named `progress`, `delta`,
`complete`, or `error`. `delta` contains a generated text fragment;
`complete` contains the validated, persisted itinerary. On failure, `error`
contains a user-safe `detail`. Streaming clients should treat a missing
`complete` event as an interrupted request.

## Follow-up questions

`POST /api/trips/{trip_id}/follow-up/stream` streams a response about a saved
itinerary. Request example:

```json
{
  "question": "Can you make the second day more relaxed?",
  "history": [
    {"role": "user", "content": "We enjoy quiet mornings."},
    {"role": "assistant", "content": "I will keep the first stop later."}
  ]
}
```

`question` is required and limited to 1,000 characters. `history` accepts up
to 12 user/assistant messages, each up to 1,200 characters. The response is an
SSE stream with `progress`, text `delta`, then an empty `complete` event.

## Saved trips

- `GET /api/trips` lists the 10 most recent saved plans.
- `GET /api/trips/{trip_id}` returns a saved itinerary or `404` when it does
  not exist.

## Research and review

- `GET /api/destinations/search?query=Kyoto` resolves a destination.
- `GET /api/weather?destination=Kyoto&days=3` returns a short Open-Meteo
  forecast. To request specific dates, pass both `start_date` and `end_date`;
  date-specific forecasts are limited to today through the next 15 days.
- `GET /api/agents/status` reports provider configuration without exposing
  credentials.
- `POST /api/budget/check` accepts `{"trip": ..., "plan": ...}` and returns
  activity subtotals and budget warnings.
- `POST /api/itinerary/validate` accepts the same shape and checks sequential
  day numbering and budget consistency.

Validation errors return `422`. Missing/invalid Groq configuration returns
`503`; upstream timeouts return `504`; unavailable providers or invalid model
output return an explicit error response.