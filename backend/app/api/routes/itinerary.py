from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.agents.validator import validate_plan
from backend.app.schemas.itinerary import TripPlan
from backend.app.schemas.trip import TripRequest
from backend.app.services.groq import GroqServiceError

router = APIRouter(prefix="/itinerary", tags=["itinerary"])


class ItineraryValidationRequest(BaseModel):
    trip: TripRequest
    plan: TripPlan


@router.post("/validate", response_model=TripPlan)
async def validate_itinerary(payload: ItineraryValidationRequest) -> TripPlan:
    try:
        return validate_plan(payload.trip, payload.plan)
    except GroqServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc