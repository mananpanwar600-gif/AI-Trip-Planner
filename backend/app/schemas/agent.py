from pydantic import BaseModel


class AgentStatus(BaseModel):
    status: str
    providers: dict[str, str]