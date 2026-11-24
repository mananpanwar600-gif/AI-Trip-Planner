import logging

from fastapi import FastAPI

from backend.app.api.router import router
from backend.app.config import get_settings

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
app = FastAPI(
    title=settings.app_name,
    description=(
        "MakeMyJourney: an AI trip planner with live travel context "
        "and streaming follow-ups."
    ),
    version=settings.app_version,
)
app.include_router(router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "name": "MakeMyJourney",
        "interface": "Streamlit",
        "streamlit_url": "http://localhost:8501",
        "api_docs": "/docs",
    }