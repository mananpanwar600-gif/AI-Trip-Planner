from backend.app.config import get_settings
from backend.app.schemas.context import Coordinates, RouteEstimate
from backend.app.tools.http import get_json
from backend.app.utils.exceptions import TravelProviderError


async def estimate_driving_route(
    origin: Coordinates, destination: Coordinates
) -> RouteEstimate:
    settings = get_settings()
    url = (
        f"{settings.osrm_base_url}/route/v1/driving/"
        f"{origin.longitude},{origin.latitude};"
        f"{destination.longitude},{destination.latitude}"
    )
    payload = await get_json(
        "OSRM",
        url,
        params={"overview": "false"},
    )
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise TravelProviderError(
            "OSRM", "A driving route could not be calculated for these locations."
        )
    route = routes[0]
    try:
        return RouteEstimate(
            distance_km=float(route["distance"]) / 1000,
            duration_hours=float(route["duration"]) / 3600,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TravelProviderError("OSRM", "OSRM returned an invalid route.") from exc