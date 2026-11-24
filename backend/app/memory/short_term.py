from backend.app.database.models import TripSummary
from backend.app.database.repositories import list_trips


def recent_trips(limit: int = 10) -> list[TripSummary]:
    return list_trips(limit=limit)