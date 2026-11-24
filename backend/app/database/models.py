from datetime import datetime

from pydantic import BaseModel

from backend.app.schemas.itinerary import TripPlan
from backend.app.schemas.trip import TripRequest


class TripSummary(BaseModel):
    trip_id: str
    destination: str
    trip_days: int
    created_at: datetime


class SavedTrip(BaseModel):
    trip_id: str
    created_at: datetime
    request: TripRequest
    plan: TripPlan