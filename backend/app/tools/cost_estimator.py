from backend.app.schemas.itinerary import CostRange, TripPlan
from backend.app.schemas.trip import TripRequest


def _fixed_range(amount: float, currency: str) -> CostRange:
    return CostRange(
        low=amount,
        high=amount,
        currency=currency,
        source_currency=currency,
    )


def _convert_range(
    amount: CostRange | None,
    target_currency: str,
    rates_to_target: dict[str, float],
) -> CostRange | None:
    if amount is None:
        return None
    source_currency = amount.currency or amount.source_currency
    if source_currency is None:
        return None
    if source_currency == target_currency:
        rate = 1.0
    else:
        rate = rates_to_target.get(source_currency)
        if rate is None:
            return None
    return CostRange(
        low=round(amount.low * rate, 2),
        high=round(amount.high * rate, 2),
        currency=target_currency,
        source_currency=source_currency,
    )


def activity_cost_subtotal(
    plan: TripPlan,
    travelers: int = 1,
    currency: str | None = None,
) -> float:
    return sum(
        activity.estimated_cost
        for day in plan.days
        for activity in day.activities
        if currency is None or activity.estimated_cost_currency == currency
    ) * travelers


def finalize_trip_budget(trip: TripRequest, plan: TripPlan) -> TripPlan:
    breakdown = plan.budget_breakdown
    sources = {fact.source for fact in plan.travel_context.facts}
    rates_to_target = plan.travel_context.exchange_rates
    unconverted_activities = False

    for day in plan.days:
        for activity in day.activities:
            source_currency = activity.estimated_cost_currency
            if source_currency is None:
                unconverted_activities = True
                continue
            activity.estimated_cost_source_currency = source_currency
            if source_currency == trip.currency:
                activity.estimated_cost_currency = trip.currency
                continue
            rate = rates_to_target.get(source_currency)
            if rate is None:
                activity.estimated_cost_currency = source_currency
                unconverted_activities = True
                continue
            activity.estimated_cost = round(activity.estimated_cost * rate, 2)
            activity.estimated_cost_currency = trip.currency

    activity_total = activity_cost_subtotal(plan, trip.travelers, trip.currency)
    breakdown.activities = (
        _fixed_range(activity_total, trip.currency)
        if activity_total > 0 or not unconverted_activities
        else None
    )
    if "Tavily destination cost research" in sources:
        breakdown.lodging = _convert_range(
            breakdown.lodging, trip.currency, rates_to_target
        )
        breakdown.meals = _convert_range(
            breakdown.meals, trip.currency, rates_to_target
        )
        breakdown.local_transport = _convert_range(
            breakdown.local_transport, trip.currency, rates_to_target
        )
        breakdown.insurance = _convert_range(
            breakdown.insurance, trip.currency, rates_to_target
        )
        breakdown.other = _convert_range(
            breakdown.other, trip.currency, rates_to_target
        )
    else:
        breakdown.lodging = None
        breakdown.meals = None
        breakdown.local_transport = None
        breakdown.insurance = None
        breakdown.other = None

    if "Tavily flight price search" in sources:
        breakdown.flights = _convert_range(
            breakdown.flights, trip.currency, rates_to_target
        )
    else:
        breakdown.flights = None
    if "Tavily visa price search" in sources:
        breakdown.visa = _convert_range(
            breakdown.visa, trip.currency, rates_to_target
        )
    else:
        breakdown.visa = None

    categories = (
        (
            "activities (some source currencies could not be converted)",
            unconverted_activities,
        ),
        ("lodging", breakdown.lodging is None),
        ("meals", breakdown.meals is None),
        ("local transport", breakdown.local_transport is None),
        ("round-trip flights", breakdown.flights is None),
        ("visa fees", breakdown.visa is None),
        ("travel insurance", breakdown.insurance is None),
        ("other costs", breakdown.other is None),
    )
    breakdown.unpriced_categories = [
        label for label, is_unpriced in categories if is_unpriced
    ]

    priced_ranges = [
        amount
        for amount in (
            breakdown.activities,
            breakdown.lodging,
            breakdown.meals,
            breakdown.local_transport,
            breakdown.flights,
            breakdown.visa,
            breakdown.insurance,
            breakdown.other,
        )
        if amount is not None
    ]
    low_total = sum(amount.low for amount in priced_ranges)
    high_total = sum(amount.high for amount in priced_ranges)
    plan.estimated_total_cost = round((low_total + high_total) / 2, 2)

    warnings = [
        warning
        for warning in plan.travel_context.warnings
        if "only the sum of listed activity costs" not in warning
        and "Some trip costs are not included" not in warning
    ]
    if breakdown.unpriced_categories:
        warnings.append(
            "Some trip costs are not included because no reliable price or "
            "convertible source currency was available: "
            + ", ".join(breakdown.unpriced_categories)
            + "."
        )
    if not rates_to_target:
        warnings.append(
            "Exchange rates were unavailable. Foreign-currency prices were not "
            "included in the converted budget."
        )
    if "Tavily destination cost research" not in sources:
        warnings.append(
            "No Tavily destination price research was available. Configure or "
            "verify TAVILY_API_KEY to source local cost estimates."
        )
        warnings.append(
            "Activity prices are AI estimates without live local price research; "
            "verify them before booking."
        )
    if "Tavily visa price search" in sources:
        warnings.append(
            "Visa estimates are generic destination fees and may vary by passport; "
            "verify requirements with the official government source."
        )
    plan.travel_context.warnings = warnings[-10:]
    return plan
