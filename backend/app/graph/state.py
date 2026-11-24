from typing import TypedDict

from backend.app.schemas.itinerary import TravelContext, TripPlan
from backend.app.schemas.trip import TripRequest


class TripState(TypedDict, total=False):
    request: TripRequest
    context: TravelContext
    plan: TripPlan