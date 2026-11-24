from fastapi import APIRouter

from backend.app.agents.budget import review_budget
from backend.app.schemas.budget import BudgetReviewRequest, BudgetReviewResponse
from backend.app.tools.cost_estimator import activity_cost_subtotal

router = APIRouter(prefix="/budget", tags=["budget"])


@router.post("/check", response_model=BudgetReviewResponse)
async def check_budget(payload: BudgetReviewRequest) -> BudgetReviewResponse:
    return BudgetReviewResponse(
        activity_subtotal=activity_cost_subtotal(payload.plan),
        estimated_total=payload.plan.estimated_total_cost,
        budget=payload.trip.budget,
        warnings=review_budget(payload.trip, payload.plan),
    )