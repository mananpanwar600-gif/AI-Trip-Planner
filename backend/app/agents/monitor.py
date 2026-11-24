from backend.app.config import get_settings


def provider_configuration() -> dict[str, str]:
    settings = get_settings()
    return {
        "groq": "configured" if settings.groq_api_key else "missing",
        "geoapify": "configured" if settings.geoapify_api_key else "optional",
        "open_meteo": "configured",
        "wikipedia": "configured",
        "wikidata": "configured",
        "osrm": "configured",
    }