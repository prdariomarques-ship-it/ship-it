from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    agent: str = Field(default="personal", description="Which agent should answer")
    contact_id: int | None = None


class ChatResponse(BaseModel):
    agent: str
    reply: str
    memories_used: int = 0
