from pydantic import BaseModel, Field

from backend.app.schemas.itinerary import TripPlan
from backend.app.schemas.trip import TripRequest


class BudgetReviewRequest(BaseModel):
    trip: TripRequest
    plan: TripPlan


class BudgetReviewResponse(BaseModel):
    activity_subtotal: float = Field(ge=0)
    estimated_total: float = Field(ge=0)
    budget: float | None = None
    warnings: list[str] = Field(default_factory=list)