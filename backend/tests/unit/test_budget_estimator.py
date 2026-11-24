from backend.app.schemas.itinerary import (
    BudgetBreakdown,
    ContextFact,
    CostRange,
    TravelContext,
    TripPlan,
)
from backend.app.schemas.trip import TripRequest
from backend.app.tools.cost_estimator import finalize_trip_budget


def _plan(
    breakdown: BudgetBreakdown,
    exchange_rates: dict[str, float],
    *,
    activity_currency: str | None = "JPY",
    include_price_sources: bool = True,
) -> TripPlan:
    facts = []
    if include_price_sources:
        facts = [
            ContextFact(
                source="Tavily destination cost research",
                detail="Budget lodging and meal price references.",
            ),
            ContextFact(
                source="Tavily flight price search",
                detail="Economy fare references.",
            ),
            ContextFact(
                source="Tavily visa price search",
                detail="Generic visitor visa fee references.",
            ),
        ]
    return TripPlan(
        destination="Kyoto",
        currency="INR",
        overview="A short trip.",
        days=[
            {
                "day": 1,
                "title": "Explore",
                "activities": [
                    {
                        "time": "09:00",
                        "name": "Visit a garden",
                        "description": "Take a walk.",
                        "location": "Kyoto",
                        "estimated_cost": 10,
                        "estimated_cost_currency": activity_currency,
                    }
                ],
            }
        ],
        estimated_total_cost=999_999,
        budget_breakdown=breakdown,
        travel_context=TravelContext(
            facts=facts,
            exchange_rates=exchange_rates,
            exchange_rate_updated_at="Tue, 24 Nov 2026 00:00:00 +0000",
        ),
    )


def test_trip_budget_converts_sourced_ranges_to_selected_currency() -> None:
    trip = TripRequest(destination="Kyoto", travelers=2, currency="INR")
    plan = _plan(
        BudgetBreakdown(
            lodging=CostRange(low=100, high=120, currency="USD"),
            meals=CostRange(low=50, high=70, currency="USD"),
            local_transport=CostRange(low=10, high=20, currency="EUR"),
            flights=CostRange(low=800, high=1_000, currency="USD"),
            visa=CostRange(low=1_000, high=1_200, currency="JPY"),
            insurance=CostRange(low=20, high=30, currency="USD"),
            other=CostRange(low=5, high=10, currency="USD"),
        ),
        {"INR": 1, "USD": 80, "EUR": 90, "JPY": 0.6},
    )

    finalized = finalize_trip_budget(trip, plan)

    assert finalized.estimated_total_cost == 90_222
    assert finalized.budget_breakdown.activities == CostRange(
        low=12,
        high=12,
        currency="INR",
        source_currency="INR",
    )
    assert finalized.budget_breakdown.flights == CostRange(
        low=64_000,
        high=80_000,
        currency="INR",
        source_currency="USD",
    )
    assert finalized.budget_breakdown.visa == CostRange(
        low=600,
        high=720,
        currency="INR",
        source_currency="JPY",
    )
    assert finalized.budget_breakdown.unpriced_categories == []


def test_prices_in_other_currencies_are_excluded_without_exchange_rates() -> None:
    trip = TripRequest(destination="Kyoto", currency="INR")
    plan = _plan(
        BudgetBreakdown(
            lodging=CostRange(low=100, high=120, currency="USD"),
            meals=CostRange(low=50, high=70, currency="USD"),
        ),
        {},
        activity_currency="USD",
        include_price_sources=False,
    )

    finalized = finalize_trip_budget(trip, plan)

    assert finalized.estimated_total_cost == 0
    assert finalized.days[0].activities[0].estimated_cost_currency == "USD"
    assert finalized.budget_breakdown.lodging is None
    assert finalized.budget_breakdown.activities is None
    assert (
        "activities (some source currencies could not be converted)"
        in finalized.budget_breakdown.unpriced_categories
    )
    assert any(
        "Exchange rates were unavailable" in warning
        for warning in finalized.travel_context.warnings
    )


def test_activity_cost_without_currency_is_not_added_to_the_budget() -> None:
    trip = TripRequest(destination="Kyoto", currency="INR")
    plan = _plan(
        BudgetBreakdown(),
        {},
        activity_currency=None,
        include_price_sources=False,
    )

    finalized = finalize_trip_budget(trip, plan)

    assert finalized.estimated_total_cost == 0
    assert finalized.budget_breakdown.activities is None
    assert finalized.days[0].activities[0].estimated_cost_currency is None
    assert (
        "activities (some source currencies could not be converted)"
        in finalized.budget_breakdown.unpriced_categories
    )
