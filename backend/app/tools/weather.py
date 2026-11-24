from datetime import date

from backend.app.config import get_settings
from backend.app.schemas.context import Coordinates, WeatherDay
from backend.app.tools.http import get_json
from backend.app.utils.exceptions import TravelProviderError
from backend.app.utils.helpers import describe_weather


async def get_forecast(
    location: Coordinates,
    days: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[WeatherDay]:
    settings = get_settings()
    if (start_date is None) != (end_date is None):
        raise TravelProviderError(
            "Open-Meteo weather",
            "Both start and end dates are required for a date-specific forecast.",
        )
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max"
        ),
        "timezone": "auto",
    }
    if start_date is not None and end_date is not None:
        forecast_days = (end_date - start_date).days + 1
        if forecast_days < 1:
            raise TravelProviderError(
                "Open-Meteo weather", "End date must be on or after start date."
            )
        if forecast_days > 16:
            raise TravelProviderError(
                "Open-Meteo weather",
                "Open-Meteo supports date-specific forecasts for up to 16 days.",
            )
        params.update(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )
    else:
        params["forecast_days"] = min(days, 16)

    payload = await get_json(
        "Open-Meteo weather",
        settings.weather_api_url,
        params=params,
    )
    daily = payload.get("daily")
    if not isinstance(daily, dict) or not isinstance(daily.get("time"), list):
        raise TravelProviderError(
            "Open-Meteo weather", "Open-Meteo returned an incomplete forecast."
        )

    forecasts = []
    for index, forecast_date in enumerate(daily["time"]):
        code = _daily_value(daily, "weather_code", index)
        precipitation = _daily_value(
            daily, "precipitation_probability_max", index
        )
        forecasts.append(
            WeatherDay(
                date=str(forecast_date),
                minimum_celsius=_as_float(
                    _daily_value(daily, "temperature_2m_min", index)
                ),
                maximum_celsius=_as_float(
                    _daily_value(daily, "temperature_2m_max", index)
                ),
                precipitation_probability=_as_int(precipitation),
                summary=describe_weather(_as_int(code) if code is not None else -1),
            )
        )
    return forecasts


def _daily_value(daily: dict, key: str, index: int):
    values = daily.get(key)
    return values[index] if isinstance(values, list) and index < len(values) else None


def _as_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None