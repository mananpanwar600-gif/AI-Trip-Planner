from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.destination import DestinationSearchResponse
from backend.app.tools.geocoding import geocode_city
from backend.app.utils.exceptions import TravelProviderError

router = APIRouter(prefix="/destinations", tags=["destinations"])


@router.get("/search", response_model=DestinationSearchResponse)
async def search_destination(
    query: str = Query(min_length=2, max_length=100),
) -> DestinationSearchResponse:
    try:
        destination = await geocode_city(query)
    except TravelProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return DestinationSearchResponse(destination=destination)