from pydantic import BaseModel, Field

from agents.executor import ExecutedStep


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    agent: str = Field(default="assistant", description="Which agent should answer")
    contact_id: int | None = None


class ChatResponse(BaseModel):
    agent: str
    reply: str
    steps: list[ExecutedStep] = []
    memories_used: int = 0
