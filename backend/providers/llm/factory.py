"""Factory for LLM providers (Factory + Strategy patterns).

Swap vendors by changing LLM_PROVIDER / EMBEDDING_PROVIDER in the environment —
no application code changes required.
"""
from functools import lru_cache

from providers.llm.anthropic.provider import AnthropicProvider
from providers.llm.base import LLMProvider
from providers.llm.gemini.provider import GeminiProvider
from providers.llm.glm.provider import GLMProvider
from providers.llm.ollama.provider import OllamaProvider
from providers.llm.openai.provider import OpenAIProvider
from utils.config import get_settings

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "glm": GLMProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}


class UnknownProviderError(ValueError):
    pass


def _build(name: str) -> LLMProvider:
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise UnknownProviderError(
            f"Unknown LLM provider {name!r}. Available: {sorted(_PROVIDERS)}"
        ) from None


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Provider used for chat/agents, selected by LLM_PROVIDER."""
    return _build(get_settings().llm_provider)


@lru_cache
def get_embedding_provider() -> LLMProvider:
    """Provider used for embeddings, selected by EMBEDDING_PROVIDER."""
    return _build(get_settings().embedding_provider)
