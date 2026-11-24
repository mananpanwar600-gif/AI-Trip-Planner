from backend.app.agents.budget import review_budget
from backend.app.schemas.itinerary import TripPlan
from backend.app.schemas.trip import TripRequest
from backend.app.services.groq import GroqServiceError


def validate_plan_shape(trip: TripRequest, plan: TripPlan) -> TripPlan:
    day_numbers = [day.day for day in plan.days]
    expected = list(range(1, trip.trip_days + 1))
    if day_numbers != expected:
        raise GroqServiceError(
            "Groq returned an itinerary with missing or out-of-order days. Please try again."
        )
    return plan


def validate_plan(trip: TripRequest, plan: TripPlan) -> TripPlan:
    plan = validate_plan_shape(trip, plan)
    budget_warnings = review_budget(trip, plan)
    if budget_warnings:
        plan.travel_context.warnings.extend(budget_warnings)
        plan.travel_context.warnings = plan.travel_context.warnings[-10:]
    return plan