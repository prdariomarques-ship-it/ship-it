"""Provider-agnostic LLM contract (Strategy pattern).

Every LLM provider translates between these neutral types and its own API,
so agents, chat and memory never depend on a specific vendor SDK.
"""
from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    """Neutral function-calling tool definition (JSON Schema parameters)."""

    name: str
    description: str
    parameters: dict = Field(default_factory=lambda: {"type": "object", "properties": {}})


class ToolCallRequest(BaseModel):
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict = {}


class ChatMessage(BaseModel):
    """Neutral chat message. role=tool carries a tool result (tool_call_id set)."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCallRequest] = []
    tool_call_id: str | None = None


class LLMResult(BaseModel):
    """Model output: free text and/or requested tool calls."""

    content: str = ""
    tool_calls: list[ToolCallRequest] = []


class EmbeddingsNotSupportedError(RuntimeError):
    """Raised by providers that don't offer an embeddings API."""


class LLMProvider(ABC):
    """Strategy interface implemented by every LLM vendor integration."""

    name: str

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """True when the provider is configured (API key present)."""

    @abstractmethod
    async def chat(self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None) -> LLMResult:
        """Run one chat turn, optionally offering function-calling tools."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return the embedding vector for a text."""


STUB_REPLY = "[IA indisponível: configure a chave de API do provedor LLM para ativar as respostas inteligentes]"
