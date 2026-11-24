from fastapi import APIRouter

from backend.app.agents.monitor import provider_configuration
from backend.app.schemas.agent import AgentStatus

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/status", response_model=AgentStatus)
async def agent_status() -> AgentStatus:
    return AgentStatus(status="ok", providers=provider_configuration())