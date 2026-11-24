from pydantic import BaseModel

from backend.app.schemas.context import Coordinates, WeatherDay


class DestinationSearchResponse(BaseModel):
    destination: Coordinates


class WeatherResponse(BaseModel):
    destination: Coordinates
    forecast: list[WeatherDay]