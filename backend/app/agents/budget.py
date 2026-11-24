from backend.app.schemas.itinerary import TripPlan
from backend.app.schemas.trip import TripRequest
from backend.app.tools.cost_estimator import activity_cost_subtotal


def review_budget(trip: TripRequest, plan: TripPlan) -> list[str]:
    warnings = []
    activity_total = activity_cost_subtotal(plan, trip.travelers, trip.currency)
    if plan.estimated_total_cost < activity_total:
        warnings.append(
            "The total estimate is lower than the sum of listed activity costs."
        )
    if trip.budget is not None and plan.budget_breakdown.unpriced_categories:
        warnings.append(
            "The budget comparison is incomplete because some trip costs are unpriced."
        )
    elif trip.budget is not None and plan.estimated_total_cost > trip.budget:
        warnings.append(
            f"The estimated total of {plan.estimated_total_cost:,.0f} {trip.currency} "
            f"is above your {trip.budget:,.0f} {trip.currency} budget."
        )
    return warnings