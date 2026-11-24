import math
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _number(name: str, default: str, legacy_name: str | None = None) -> float:
    value = os.environ.get(name)
    if value is None and legacy_name:
        value = os.environ.get(legacy_name)
    try:
        return float(value if value is not None else default)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number.") from exc


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    groq_api_key: str
    groq_model: str
    groq_model_extra: str
    groq_temperature: float
    groq_timeout: float
    external_api_timeout: float
    tavily_api_key: str
    exchange_rate_api_key: str
    geoapify_api_key: str
    weather_api_url: str
    weather_geocoding_url: str
    osrm_base_url: str
    nominatim_base_url: str
    nominatim_user_agent: str
    wikidata_sparql_url: str
    wikipedia_api_url: str
    database_url: str
    log_level: str
    api_host: str
    api_port: int


def get_settings() -> Settings:
    try:
        api_port = int(os.environ.get("API_PORT", "8000"))
    except ValueError as exc:
        raise RuntimeError("API_PORT must be an integer.") from exc

    temperature = _number("GROQ_TEMPERATURE", "0.2", "GROQ_TEMPRATURE")
    timeout = _number("GROQ_TIMEOUT", "60")
    external_timeout = _number("EXTERNAL_API_TIMEOUT", "12")
    if not math.isfinite(temperature) or not 0 <= temperature <= 2:
        raise RuntimeError("GROQ_TEMPERATURE must be between 0 and 2.")
    if not math.isfinite(timeout) or timeout <= 0:
        raise RuntimeError("GROQ_TIMEOUT must be greater than zero.")
    if not math.isfinite(external_timeout) or external_timeout <= 0:
        raise RuntimeError("EXTERNAL_API_TIMEOUT must be greater than zero.")
    if not 1 <= api_port <= 65535:
        raise RuntimeError("API_PORT must be between 1 and 65535.")

    return Settings(
        app_name=os.environ.get("APP_NAME", "MakeMyJourney"),
        app_version=os.environ.get("APP_VERSION", "1.0.0"),
        groq_api_key=os.environ.get("GROQ_API_KEY", "").strip(),
        groq_model=os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b").strip(),
        groq_model_extra=os.environ.get("GROQ_MODEL_EXTRA", "").strip(),
        groq_temperature=temperature,
        groq_timeout=timeout,
        external_api_timeout=external_timeout,
        tavily_api_key=os.environ.get("TAVILY_API_KEY", "").strip(),
        exchange_rate_api_key=os.environ.get("EXCHANGE_RATE_API_KEY", "").strip(),
        geoapify_api_key=os.environ.get("GEOAPIFY_API_KEY", "").strip(),
        weather_api_url=os.environ.get(
            "WEATHER_API_URL", "https://api.open-meteo.com/v1/forecast"
        ),
        weather_geocoding_url=os.environ.get(
            "WEATHER_GEOCODING_URL",
            "https://geocoding-api.open-meteo.com/v1/search",
        ),
        osrm_base_url=os.environ.get(
            "OSRM_BASE_URL", "https://router.project-osrm.org"
        ).rstrip("/"),
        nominatim_base_url=os.environ.get(
            "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
        ).rstrip("/"),
        nominatim_user_agent=os.environ.get(
            "NOMINATIM_USER_AGENT", "MakeMyJourney/1.0 (local development)"
        ),
        wikidata_sparql_url=os.environ.get(
            "WIKIDATA_SPARQL_URL", "https://query.wikidata.org/sparql"
        ),
        wikipedia_api_url=os.environ.get(
            "WIKIPEDIA_API_URL", "https://en.wikipedia.org/w/api.php"
        ),
        database_url=os.environ.get(
            "DATABASE_URL", "sqlite+aiosqlite:///./travelops.db"
        ),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        api_host=os.environ.get("API_HOST", "127.0.0.1"),
        api_port=api_port,
    )