from backend.app.schemas.context import Coordinates
from backend.app.schemas.itinerary import ContextFact
from backend.app.tools.places import get_nearby_places


async def find_accommodation_facts(
    destination: Coordinates,
) -> list[ContextFact]:
    places = await get_nearby_places(
        destination,
        limit=4,
        categories="accommodation.hotel,accommodation.hostel",
    )
    return [
        ContextFact(
            source="Geoapify accommodation",
            detail=f"{place.name} — {place.address}",
        )
        for place in places
    ]