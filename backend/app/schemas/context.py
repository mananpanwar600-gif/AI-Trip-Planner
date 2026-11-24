from pydantic import BaseModel, Field


class Coordinates(BaseModel):
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    region: str | None = None
    country: str | None = None
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")


class WeatherDay(BaseModel):
    date: str
    minimum_celsius: float | None = None
    maximum_celsius: float | None = None
    precipitation_probability: int | None = None
    summary: str


class NearbyPlace(BaseModel):
    name: str
    address: str
    category: str | None = None


class RouteEstimate(BaseModel):
    distance_km: float = Field(ge=0)
    duration_hours: float = Field(ge=0)


class DestinationResearch(BaseModel):
    facts: list[str] = Field(default_factory=list, max_length=6)
