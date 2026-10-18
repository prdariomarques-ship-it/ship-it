from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agents.executor import ExecutedStep

# Campos que só existem em /chat/ocr. Chegando em /chat, o pedido é recusado (422) antes de qualquer agente.
# Os demais campos desconhecidos continuam ignorados, como no contrato antigo: clientes existentes não quebram.
OCR_ONLY_FIELDS = frozenset({"ocr_source_message_id", "expected_instance"})


class ChatRequest(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _reject_ocr_fields(cls, data: Any) -> Any:
        if isinstance(data, dict) and OCR_ONLY_FIELDS & data.keys():
            raise ValueError("OCR requests must use POST /chat/ocr")
        return data

    message: str = Field(min_length=1)
    agent: str = Field(default="assistant", description="Which agent should answer")
    contact_id: int | None = None


class OCRChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=20000)
    contact_id: int = Field(gt=0)
    ocr_source_message_id: int = Field(gt=0)
    expected_instance: str = Field(min_length=1, max_length=255)


class ChatResponse(BaseModel):
    agent: str
    reply: str
    steps: list[ExecutedStep] = []
    memories_used: int = 0
