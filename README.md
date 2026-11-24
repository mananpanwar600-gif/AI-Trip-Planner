# MakeMyJourney

MakeMyJourney is a practical AI trip planner with a simple Streamlit interface.
It gathers optional live destination context, asks the Groq model configured in
your environment for a structured itinerary, saves completed trips locally, and
streams follow-up answers grounded in the saved plan.

## Features

- Calculates trip length from the required inclusive start and end dates.
- Personalizes plans by destination, origin, travelers, budget, currency, pace,
  interests, and additional needs.
- Uses verified state/region context and localized research to keep Indian
  itineraries focused on the right state or union territory.
- Shows an itemized whole-trip budget with Tavily-sourced price ranges converted
  into the selected currency using ExchangeRate-API rates.
- Shows linked price research in a concise table and omits results without a
  usable source link.
- Streams Groq itinerary generation and follow-up responses.
- Adds optional weather, place, accommodation, route, and destination research.
- Validates day ordering and itinerary shape before storing a plan.
- Saves plans and inputs in local SQLite; reopen or delete recent trips from the
  sidebar.
- Keeps API keys in the Python process; they are never sent to the browser.
- Provides an optional FastAPI JSON/SSE API alongside the Streamlit app.

Research and prices are suggestions, not guarantees. Verify important details
with official providers before booking or travel.
Open-Meteo provides forecasts for up to 16 days; dates beyond that window are
still used for planning, but the app warns that weather is not forecastable yet.

## Requirements

- Python 3.13 or newer
- A Groq API key and a model available to that key
- Windows PowerShell, macOS, or Linux shell

## Install and run (Windows PowerShell)

Run these commands from the project directory:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Set `GROQ_API_KEY` and `GROQ_MODEL` in your local `.env`, then start the
Streamlit app:

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Open <http://localhost:8501>. The Streamlit process calls the planner services
directly, so you do not need to start Uvicorn for the main app.
After installing the package, `makemyjourney` is an equivalent launcher.

The optional FastAPI JSON API can be run in a second terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Its API reference is at <http://127.0.0.1:8000/docs>, and its health endpoint is
at <http://127.0.0.1:8000/api/health>. `API_HOST` and `API_PORT` configure the
API CLI (`makemyjourney-api` after package installation).

## Environment configuration

The application loads the project `.env` into the process environment and reads
settings through `os.environ`. Use `.env.example` as the reference; if `.env`
already exists, preserve its secrets and add or change only settings you need.
Do not commit the real `.env` or expose keys in frontend code.

| Variable | Purpose |
| --- | --- |
| `APP_NAME`, `APP_VERSION` | FastAPI metadata and version |
| `GROQ_API_KEY` | Required server-side Groq credential |
| `GROQ_MODEL` | Model used for itineraries and follow-ups |
| `GROQ_MODEL_EXTRA` | Optional fallback model used when `GROQ_MODEL` is rate-limited |
| `GROQ_TEMPERATURE` | Model temperature from 0 to 2 |
| `GROQ_TIMEOUT` | Groq timeout in seconds |
| `TAVILY_API_KEY` | Optional Tavily key for sourced destination-price and flight research |
| `EXCHANGE_RATE_API_KEY` | ExchangeRate-API key for foreign-currency conversion |
| `GEOAPIFY_API_KEY` | Optional nearby places and accommodation data |
| `EXTERNAL_API_TIMEOUT` | Timeout for travel research requests |
| `WEATHER_API_URL` | Open-Meteo forecast endpoint |
| `WEATHER_GEOCODING_URL` | Open-Meteo location lookup endpoint |
| `OSRM_BASE_URL` | Route calculation service |
| `NOMINATIM_BASE_URL`, `NOMINATIM_USER_AGENT` | Fallback geocoder settings |
| `WIKIPEDIA_API_URL`, `WIKIDATA_SPARQL_URL` | Destination research endpoints |
| `DATABASE_URL` | File-backed SQLite database location |
| `LOG_LEVEL` | Backend logging level |
| `API_HOST`, `API_PORT` | Optional FastAPI server binding |

Open-Meteo, Nominatim, OSRM, Wikipedia, and Wikidata need no project API key for
the current usage. Geoapify is optional. If a research source is unavailable,
the app keeps planning and reports the limitation in the research notes.
Tavily search results are estimates, not bookable fares. Flight estimates require
an origin and selected travel dates. ExchangeRate-API rates are applied to source
currencies and the response date is shown in the budget breakdown. Visa prices
from generic search results may not apply to every passport. Categories without a
sourced price or convertible currency are excluded from the priced subtotal and
listed as unpriced.

## Streaming and follow-ups

Itinerary generation streams from Groq while Streamlit reports research and
generation progress. Invalid JSON responses receive one correction retry, then
the structured response is validated and persisted before it is displayed as a
complete itinerary. Follow-up answers stream as readable text into the chat;
recent user/assistant turns are bounded and sent with the saved plan to the
configured model.

The optional API also offers:

- `POST /api/trips/plan/stream` — progress and itinerary SSE events.
- `POST /api/trips/{trip_id}/follow-up/stream` — streamed follow-up SSE events.
- `POST /api/trips/plan` — regular JSON itinerary response.

See [API documentation](docs/api_documentation.md) and `/docs` for the full API.

## Tests and checks

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe -m ruff check backend scripts src streamlit_app.py
.\.venv\Scripts\python.exe -m compileall -q backend scripts src streamlit_app.py
```

Tests mock provider responses and do not consume Groq quota or confirm that your
credentials are valid. Live calls can be rate-limited by the provider.

## Troubleshooting

- **Groq key missing (`503`):** Set `GROQ_API_KEY` in `.env`, then restart
  Streamlit.
- **Rate limited:** Wait for the provider limit to clear; the app does not retry
  automatically unless `GROQ_MODEL_EXTRA` is configured, in which case it retries
  once with that model.
- **Unexpected model output:** The plan is validated before saving. Retry when
  the provider is available; if the model omits a trip total, the app can label
  the sum of listed activity costs as a subtotal.
- **Research warnings:** Optional providers can fail independently without
  preventing itinerary generation.
- **Database unavailable:** Ensure `DATABASE_URL` points to a writable,
  file-backed SQLite database.

## Project layout

```text
streamlit_app.py       Streamlit entry point
src/trip_planner/      Installed MakeMyJourney launcher
backend/app/
  agents/              Research, planning, budget, and validation
  api/                 Optional FastAPI JSON/SSE routes
  database/            SQLite persistence
  graph/               Research and planning workflow
  schemas/             Validated requests and responses
  services/            Groq, travel context, and trip services
  tools/               External travel data integrations
backend/tests/          Mocked unit and API tests
docs/                   API, architecture, and workflow notes
```
