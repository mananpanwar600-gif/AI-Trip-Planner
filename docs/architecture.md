# Architecture

MakeMyJourney's interface is a Streamlit app (`streamlit_app.py`). It uses the
same Python services and SQLite persistence as the optional FastAPI service;
the UI does not need a separate API server. FastAPI exposes JSON/SSE endpoints
for other clients. Provider credentials stay in the Python process.

The trip workflow is sequential at the top level and parallel for independent
research:

1. The supervisor checks that `GROQ_API_KEY` is configured.
2. The researcher resolves the destination with Open-Meteo, falling back to
   Nominatim when necessary.
3. Weather, Geoapify places and accommodation, Wikipedia, and Wikidata are
   queried concurrently. Selected trip dates are used for weather when they
   fall within Open-Meteo's 16-day forecast window. A driving route is added
   when an origin is supplied.
4. The planner streams a JSON response from the `GROQ_MODEL` configured in
   `.env`; Streamlit shows live progress while the response is assembled.
5. Pydantic validates the itinerary; the validator checks day numbering and
   surfaces budget mismatches before the plan is saved in SQLite.
6. Follow-up questions use the saved request and itinerary as context and stream
   a bounded-history response in the trip conversation.

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