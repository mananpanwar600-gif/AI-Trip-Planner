from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.destination import WeatherResponse
from backend.app.tools.geocoding import geocode_city
from backend.app.tools.weather import get_forecast
from backend.app.utils.exceptions import TravelProviderError

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("", response_model=WeatherResponse)
async def destination_weather(
    destination: str = Query(min_length=2, max_length=100),
    days: int = Query(default=3, ge=1, le=16),
    start_date: date | None = None,
    end_date: date | None = None,
) -> WeatherResponse:
    if (start_date is None) != (end_date is None):
        raise HTTPException(
            status_code=422,
            detail="Both start_date and end_date are required.",
        )
    if start_date is not None and end_date is not None:
        if end_date < start_date:
            raise HTTPException(
                status_code=422,
                detail="end_date must be on or after start_date.",
            )
        if (end_date - start_date).days >= 16:
            raise HTTPException(
                status_code=422,
                detail="Date-specific forecasts can cover up to 16 days.",
            )
        today = date.today()
        if start_date < today or end_date > today + timedelta(days=15):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Open-Meteo forecasts are available from today through "
                    f"{(today + timedelta(days=15)).isoformat()}."
                ),
            )
    try:
        location = await geocode_city(destination)
        if start_date is not None and end_date is not None:
            days = (end_date - start_date).days + 1
            forecast = await get_forecast(
                location,
                days,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            forecast = await get_forecast(location, days)
    except TravelProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return WeatherResponse(destination=location, forecast=forecast)