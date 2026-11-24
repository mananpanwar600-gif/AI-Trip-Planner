from datetime import date

from backend.app.schemas.context import Coordinates, WeatherDay
from backend.app.schemas.itinerary import ContextFact
from backend.app.tools.weather import get_forecast


async def get_weather_facts(
    destination: Coordinates,
    days: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[ContextFact]:
    forecast = await get_forecast(destination, days, start_date, end_date)
    return [_format_weather_fact(day) for day in forecast]


def _format_weather_fact(day: WeatherDay) -> ContextFact:
    temperatures = []
    if day.minimum_celsius is not None:
        temperatures.append(f"low {day.minimum_celsius:.0f} C")
    if day.maximum_celsius is not None:
        temperatures.append(f"high {day.maximum_celsius:.0f} C")
    if day.precipitation_probability is not None:
        temperatures.append(
            f"{day.precipitation_probability}% precipitation chance"
        )
    return ContextFact(
        source="Open-Meteo forecast",
        detail=f"{day.date}: {', '.join([day.summary, *temperatures])}.",
    )