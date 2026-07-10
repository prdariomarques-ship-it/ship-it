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


class TokenUsage(BaseModel):
    """Token accounting for one chat call, when the provider reports it."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )


class LLMResult(BaseModel):
    """Model output: free text and/or requested tool calls."""

    content: str = ""
    tool_calls: list[ToolCallRequest] = []
    usage: TokenUsage = Field(default_factory=TokenUsage)


class EmbeddingsNotSupportedError(RuntimeError):
    """Raised by providers that don't offer an embeddings API."""


# Approximate public list pricing (USD per 1M tokens), accurate as of each
# provider's integration into Dario OS — update here as vendors reprice.
# Providers without per-token billing (self-hosted Ollama) or without a
# tracked price (GLM, region/plan-dependent) estimate as zero rather than
# guessing; treat this as a rough operating signal, not an invoice.
_PRICING_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "openai": (0.15, 0.60),  # gpt-4o-mini
    "anthropic": (3.00, 15.00),  # claude-sonnet family
    "gemini": (0.075, 0.30),  # gemini-2.0-flash
    "glm": (0.0, 0.0),
    "ollama": (0.0, 0.0),
}


def estimate_cost_usd(provider_name: str, usage: TokenUsage) -> float:
    """Rough cost estimate from the static table above."""
    prompt_price, completion_price = _PRICING_PER_MILLION_TOKENS.get(provider_name, (0.0, 0.0))
    return (usage.prompt_tokens * prompt_price + usage.completion_tokens * completion_price) / 1_000_000


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
