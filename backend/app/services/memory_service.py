from backend.app.database.models import SavedTrip, TripSummary
from backend.app.database.repositories import delete_trip, get_trip
from backend.app.memory.short_term import recent_trips


def list_recent_trips(limit: int = 10) -> list[TripSummary]:
    return recent_trips(limit=limit)


def load_trip(trip_id: str) -> SavedTrip | None:
    return get_trip(trip_id)


def delete_saved_trip(trip_id: str) -> bool:
    return delete_trip(trip_id)