from backend.app.schemas.context import Coordinates
from backend.app.schemas.itinerary import ContextFact
from backend.app.tools.routing import estimate_driving_route


async def get_route_fact(
    origin: Coordinates, destination: Coordinates
) -> ContextFact:
    route = await estimate_driving_route(origin, destination)
    return ContextFact(
        source="OSRM",
        detail=(
            f"Approximate driving distance from {origin.name} to "
            f"{destination.name}: {route.distance_km:.0f} km "
            f"({route.duration_hours:.1f} hours)."
        ),
    )