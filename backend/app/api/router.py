from fastapi import APIRouter

from backend.app.agents.monitor import provider_configuration
from backend.app.api.routes import (
    agents,
    budget,
    destinations,
    itinerary,
    trips,
    weather,
)

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict[str, object]:
    return {"status": "ok", "providers": provider_configuration()}

router.include_router(trips.router)
router.include_router(agents.router)
router.include_router(budget.router)
router.include_router(destinations.router)
router.include_router(itinerary.router)
router.include_router(weather.router)