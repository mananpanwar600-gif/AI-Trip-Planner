from backend.app.config import get_settings
from backend.app.tools.http import get_json
from backend.app.utils.exceptions import TravelProviderError
from backend.app.utils.helpers import strip_html


async def research_destination(destination: str) -> list[str]:
    wikipedia = await search_wikipedia(destination)
    wikidata = await search_wikidata(destination)
    return wikipedia + wikidata


async def search_wikipedia(destination: str) -> list[str]:
    settings = get_settings()
    return await _wikipedia_facts(settings.wikipedia_api_url, destination)


async def search_wikidata(destination: str) -> list[str]:
    settings = get_settings()
    return await _wikidata_facts(settings.wikidata_sparql_url, destination)


async def _wikipedia_facts(url: str, destination: str) -> list[str]:
    payload = await get_json(
        "Wikipedia",
        url,
        params={
            "action": "query",
            "list": "search",
            "srsearch": f"{destination} travel attractions",
            "srlimit": 3,
            "format": "json",
        },
        headers={"User-Agent": "MakeMyJourney/1.0 (travel research)"},
    )
    query = payload.get("query")
    if not isinstance(query, dict) or not isinstance(query.get("search"), list):
        raise TravelProviderError("Wikipedia", "Wikipedia returned invalid search data.")
    results = query["search"]
    facts = []
    for result in results:
        if not isinstance(result, dict):
            continue
        title = result.get("title")
        snippet = strip_html(str(result.get("snippet", "")))
        if title and snippet:
            facts.append(f"Wikipedia — {title}: {snippet}")
    return facts


async def _wikidata_facts(url: str, destination: str) -> list[str]:
    safe_destination = (
        destination.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", " ")
    )
    query = (
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
        "PREFIX schema: <http://schema.org/> "
        "SELECT ?description WHERE { "
        f'?item rdfs:label "{safe_destination}"@en; '
        "schema:description ?description. "
        'FILTER(LANG(?description) = "en") } LIMIT 2'
    )
    payload = await get_json(
        "Wikidata",
        url,
        params={"query": query, "format": "json"},
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": "MakeMyJourney/1.0 (travel research)",
        },
    )
    results = payload.get("results", {})
    bindings = results.get("bindings", []) if isinstance(results, dict) else []
    if not isinstance(bindings, list):
        raise TravelProviderError("Wikidata", "Wikidata returned invalid search data.")
    facts = []
    for binding in bindings:
        description = binding.get("description", {}) if isinstance(binding, dict) else {}
        value = description.get("value") if isinstance(description, dict) else None
        if value:
            facts.append(f"Wikidata: {value}")
    return facts