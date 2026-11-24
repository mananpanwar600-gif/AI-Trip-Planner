from backend.app.config import get_settings
from backend.app.schemas.context import Coordinates, NearbyPlace
from backend.app.tools.http import get_json
from backend.app.utils.exceptions import TravelProviderError


async def get_nearby_places(
    location: Coordinates,
    limit: int = 6,
    categories: str = (
        "tourism.attraction,entertainment.museum,catering.restaurant"
    ),
) -> list[NearbyPlace]:
    settings = get_settings()
    if not settings.geoapify_api_key:
        raise TravelProviderError(
            "Geoapify", "GEOAPIFY_API_KEY is not configured; nearby places were skipped."
        )

    payload = await get_json(
        "Geoapify",
        "https://api.geoapify.com/v2/places",
        params={
            "categories": categories,
            "filter": (
                f"circle:{location.longitude},{location.latitude},5000"
            ),
            "bias": f"proximity:{location.longitude},{location.latitude}",
            "limit": limit,
            "apiKey": settings.geoapify_api_key,
        },
    )
    features = payload.get("features")
    if not isinstance(features, list):
        raise TravelProviderError("Geoapify", "Geoapify returned invalid places data.")

    places = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties", {})
        if not isinstance(properties, dict):
            continue
        name = properties.get("name")
        address = properties.get("formatted")
        if not name or not address:
            continue
        categories = properties.get("categories", [])
        places.append(
            NearbyPlace(
                name=str(name),
                address=str(address),
                category=str(categories[0]) if categories else None,
            )
        )
    return places