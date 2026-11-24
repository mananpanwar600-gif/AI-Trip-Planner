from datetime import date, timedelta

import pytest

from backend.app.agents.validator import validate_plan
from backend.app.schemas.itinerary import Activity, DayPlan, TripPlan
from backend.app.schemas.trip import TripRequest
from backend.app.services.groq import GroqServiceError


def test_trip_request_accepts_pace_and_additional_preferences() -> None:
    trip = TripRequest(
        destination="Kyoto",
        pace="relaxed",
        additional_preferences="Vegetarian meals; avoid long walks.",
    )

    assert trip.pace == "relaxed"
    assert trip.additional_preferences.startswith("Vegetarian")


def test_trip_request_rejects_oversized_additional_preferences() -> None:
    with pytest.raises(ValueError):
        TripRequest(
            destination="Kyoto",
            additional_preferences="x" * 501,
        )


def test_trip_dates_set_inclusive_duration() -> None:
    start_date = date.today() + timedelta(days=2)
    trip = TripRequest(
        destination="Kyoto",
        trip_days=1,
        start_date=start_date,
        end_date=start_date + timedelta(days=2),
    )

    assert trip.trip_days == 3


def test_trip_dates_require_a_complete_valid_range() -> None:
    start_date = date.today() + timedelta(days=2)
    with pytest.raises(ValueError, match="Both start and end dates"):
        TripRequest(destination="Kyoto", start_date=start_date)
    with pytest.raises(ValueError, match="End date must be on or after"):
        TripRequest(
            destination="Kyoto",
            start_date=start_date,
            end_date=start_date - timedelta(days=1),
        )


def test_validator_flags_plan_over_budget() -> None:
    trip = TripRequest(destination="Kyoto", trip_days=1, budget=50)
    plan = TripPlan(
        destination="Kyoto",
        currency="USD",
        overview="A short city break.",
        days=[
            DayPlan(
                day=1,
                title="Explore the city",
                activities=[
                    Activity(
                        time="09:00",
                        name="Visit a garden",
                        description="Take a morning walk.",
                        location="Kyoto",
                        estimated_cost=20,
                    )
                ],
            )
        ],
        estimated_total_cost=75,
    )

    validated = validate_plan(trip, plan)

    assert any(
        "above your 50 USD budget" in warning
        for warning in validated.travel_context.warnings
    )


def test_validator_rejects_misnumbered_days() -> None:
    trip = TripRequest(destination="Kyoto", trip_days=2)
    plan = TripPlan(
        destination="Kyoto",
        overview="A short city break.",
        days=[
            DayPlan(
                day=1,
                title="First day",
                activities=[
                    Activity(
                        time="09:00",
                        name="Visit a garden",
                        description="Take a morning walk.",
                        location="Kyoto",
                        estimated_cost=20,
                    )
                ],
            ),
            DayPlan(
                day=3,
                title="Third day",
                activities=[
                    Activity(
                        time="09:00",
                        name="Visit a temple",
                        description="Explore a local temple.",
                        location="Kyoto",
                        estimated_cost=10,
                    )
                ],
            ),
        ],
        estimated_total_cost=75,
    )

    with pytest.raises(GroqServiceError, match="missing or out-of-order"):
        validate_plan(trip, plan)
