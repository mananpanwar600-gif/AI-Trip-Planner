from collections.abc import Awaitable, Callable
from typing import TypedDict

from backend.app.schemas.itinerary import TravelContext, TripPlan
from backend.app.schemas.trip import TripRequest

TokenCallback = Callable[[str], Awaitable[None]]


class TripState(TypedDict, total=False):
    request: TripRequest
    context: TravelContext
    plan: TripPlan
    on_token: TokenCallback | None