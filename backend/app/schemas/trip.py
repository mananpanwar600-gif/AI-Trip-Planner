from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TripRequest(BaseModel):
    destination: str = Field(min_length=2, max_length=100)
    origin: str | None = Field(default=None, max_length=100)
    trip_days: int = Field(default=3, ge=1, le=21)
    start_date: date | None = None
    end_date: date | None = None
    budget: float | None = Field(default=None, gt=0, le=1_000_000)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    travelers: int = Field(default=1, ge=1, le=20)
    travel_style: Literal["budget", "mid-range", "upscale"] = "budget"
    interests: list[str] = Field(default_factory=list, max_length=10)
    pace: Literal["relaxed", "balanced", "active"] = "balanced"
    additional_preferences: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def derive_trip_days_from_dates(self) -> "TripRequest":
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Both start and end dates are required.")
        if self.start_date is not None and self.end_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("End date must be on or after the start date.")
            duration = (self.end_date - self.start_date).days + 1
            if duration > 21:
                raise ValueError("Trip date range cannot exceed 21 days.")
            self.trip_days = duration
        return self

    @field_validator("destination", "origin")
    @classmethod
    def strip_location(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Location cannot be blank.")
        return cleaned

    @field_validator("interests")
    @classmethod
    def clean_interests(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if any(len(value) > 60 for value in cleaned):
            raise ValueError("Each interest must be 60 characters or fewer.")
        return cleaned

    @field_validator("additional_preferences")
    @classmethod
    def clean_additional_preferences(cls, value: str) -> str:
        return value.strip()