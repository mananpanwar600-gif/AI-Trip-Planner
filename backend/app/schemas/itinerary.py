from pydantic import AliasChoices, AnyHttpUrl, BaseModel, Field, model_validator


class ContextFact(BaseModel):
    source: str
    detail: str
    title: str | None = None
    url: AnyHttpUrl | None = None


class TravelContext(BaseModel):
    facts: list[ContextFact] = Field(default_factory=list, max_length=40)
    warnings: list[str] = Field(default_factory=list, max_length=10)
    exchange_rates: dict[str, float] = Field(default_factory=dict)
    exchange_rate_updated_at: str | None = None


class Activity(BaseModel):
    time: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=2, max_length=500)
    location: str = Field(min_length=2, max_length=160)
    estimated_cost: float = Field(ge=0)
    estimated_cost_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    estimated_cost_source_currency: str | None = Field(
        default=None, pattern=r"^[A-Z]{3}$"
    )


class DayPlan(BaseModel):
    day: int = Field(ge=1)
    title: str = Field(min_length=2, max_length=120)
    activities: list[Activity] = Field(min_length=1, max_length=8)


class CostRange(BaseModel):
    low: float = Field(ge=0)
    high: float = Field(ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    source_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def validate_order(self) -> "CostRange":
        if self.high < self.low:
            raise ValueError("Cost range high must be greater than or equal to low.")
        return self


class BudgetBreakdown(BaseModel):
    activities: CostRange | None = None
    lodging: CostRange | None = None
    meals: CostRange | None = None
    local_transport: CostRange | None = None
    flights: CostRange | None = None
    visa: CostRange | None = None
    insurance: CostRange | None = None
    other: CostRange | None = None
    unpriced_categories: list[str] = Field(default_factory=list)


class TripPlan(BaseModel):
    trip_id: str | None = None
    destination: str = Field(min_length=2, max_length=100)
    currency: str = "USD"
    overview: str = Field(min_length=2, max_length=1000)
    days: list[DayPlan] = Field(min_length=1, max_length=21)
    estimated_total_cost: float = Field(
        ge=0,
        validation_alias=AliasChoices(
            "estimated_total_cost",
            "estimated_budget",
            "total_estimated_cost",
            "total_cost",
        ),
    )
    budget_breakdown: BudgetBreakdown = Field(default_factory=BudgetBreakdown)
    tips: list[str] = Field(default_factory=list, max_length=8)
    travel_context: TravelContext = Field(default_factory=TravelContext)