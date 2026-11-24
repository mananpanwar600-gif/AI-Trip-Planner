from backend.app.config import get_settings
from backend.app.schemas.context import Coordinates
from backend.app.tools.http import get_json
from backend.app.utils.exceptions import TravelProviderError


async def geocode_city(query: str) -> Coordinates:
    settings = get_settings()
    open_meteo_error: TravelProviderError | None = None
    try:
        payload = await get_json(
            "Open-Meteo geocoding",
            settings.weather_geocoding_url,
            params={"name": query, "count": 1, "language": "en", "format": "json"},
        )
        results = payload.get("results", [])
        if isinstance(results, list) and results:
            result = results[0]
            if not isinstance(result, dict):
                raise TypeError("Invalid location result.")
            return Coordinates(
                name=result.get("name", query),
                latitude=float(result["latitude"]),
                longitude=float(result["longitude"]),
                region=result.get("admin1"),
                country=result.get("country"),
                country_code=(
                    result.get("country_code", "").upper()
                    if isinstance(result.get("country_code"), str)
                    else None
                ),
            )
    except (TravelProviderError, KeyError, TypeError, ValueError) as exc:
        open_meteo_error = (
            exc
            if isinstance(exc, TravelProviderError)
            else TravelProviderError("Open-Meteo geocoding", "Invalid location result.")
        )

    try:
        results = await get_json(
            "Nominatim",
            f"{settings.nominatim_base_url}/search",
            params={"q": query, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": settings.nominatim_user_agent},
        )
    except TravelProviderError as exc:
        if open_meteo_error:
            raise TravelProviderError(
                "Geocoding", "Could not look up the destination right now."
            ) from exc
        raise

    if not isinstance(results, list) or not results:
        raise TravelProviderError(
            "Geocoding", f"Could not find a location for “{query}”."
        ) from open_meteo_error
    result = results[0]
    try:
        address = result.get("address", {})
        if not isinstance(address, dict):
            address = {}
        return Coordinates(
            name=result.get("name") or result.get("display_name", query).split(",")[0],
            latitude=float(result["lat"]),
            longitude=float(result["lon"]),
            region=address.get("state") or address.get("region"),
            country=address.get("country"),
            country_code=(
                address.get("country_code", "").upper()
                if isinstance(address.get("country_code"), str)
                else None
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TravelProviderError(
            "Nominatim", "Nominatim returned an invalid location."
        ) from exc