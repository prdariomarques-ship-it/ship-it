from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1)
    source: str = Field(default="manual", max_length=100)
    contact_id: int | None = None


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int | None
    source: str
    content: str
    vector_id: str
    created_at: datetime


class MemorySearchResult(BaseModel):
    content: str
    source: str
    contact_id: int | None
    score: float
