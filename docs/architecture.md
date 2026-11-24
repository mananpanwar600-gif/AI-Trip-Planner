# Architecture

MakeMyJourney's interface is a Streamlit app (`streamlit_app.py`). It uses the
same Python services and SQLite persistence as the optional FastAPI service;
the UI does not need a separate API server. FastAPI exposes JSON/SSE endpoints
for other clients. Provider credentials stay in the Python process.

LangGraph orchestrates specialist trip agents over shared typed state. The same
workflow is used by the Streamlit app and JSON/SSE planning endpoints:

1. The supervisor checks the request and `GROQ_API_KEY`.
2. The researcher resolves the destination with Open-Meteo, falling back to
   Nominatim when necessary.
3. Weather, Geoapify places and accommodation, Wikipedia, and Wikidata are
   queried concurrently. Selected trip dates are used for weather when they
   fall within Open-Meteo's 16-day forecast window. A driving route is added
   when an origin is supplied.
4. The planner uses LangChain chat prompt templates and streams a JSON response
   from the `GROQ_MODEL` configured in `.env`.
5. A budget reviewer annotates budget mismatches, then the validator checks
   day numbering before the plan is saved in SQLite.
6. Follow-up questions use the saved request and itinerary as context and stream
   a bounded-history response in the trip conversation.

Groq requests remain on the existing OpenAI-compatible HTTP integration so
model fallback, response repair, and token filtering remain consistent.
LangChain owns prompt composition, and LangGraph owns multi-agent execution.

Live research sources are optional. A provider failure is returned as a visible
context warning; a missing Groq key or a failed/invalid Groq response is an
explicit API error. No keys or raw upstream error bodies are sent to the
browser.

## Configuration

`backend/app/config.py` loads the root `.env` into the process environment and
reads settings through `os.environ`. It accepts both `GROQ_TEMPERATURE` and the
older `GROQ_TEMPRATURE` spelling. `.env.example` contains placeholders only.

Open-Meteo, Nominatim, OSRM, Wikipedia, and Wikidata do not require project API
keys for the current usage. Geoapify place search is enabled when
`GEOAPIFY_API_KEY` is present.