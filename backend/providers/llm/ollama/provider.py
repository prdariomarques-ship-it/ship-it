"""Ollama provider — local/self-hosted models via Ollama's OpenAI-compatible API.

Ollama (>= 0.1.24) exposes `/v1/chat/completions` with the same wire format
as OpenAI, tool calling included for models that support it (e.g. llama3.1,
qwen2.5). Reusing OpenAIProvider — same trick as GLM — means this provider is
a configuration, not a reimplementation: point `base_url` at the local
Ollama instance and skip the API key (Ollama doesn't require one by default).
"""
from providers.llm.base import EmbeddingsNotSupportedError
from providers.llm.openai.provider import OpenAIProvider
from utils.config import get_settings


class OllamaProvider(OpenAIProvider):
    name = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        super().__init__(
            api_key="ollama",  # the OpenAI SDK requires a non-empty key; Ollama ignores it
            base_url=base_url if base_url is not None else settings.ollama_base_url,
            model=model or settings.ollama_model,
        )

    @property
    def enabled(self) -> bool:
        # No API key gates a local model; the base_url being configured is enough.
        return bool(self._base_url)

    async def embed(self, text: str) -> list[float]:
        # Embedding dimension depends entirely on the locally pulled model
        # (768 for nomic-embed-text, 1024 for mxbai-embed-large, ...) and is
        # never guaranteed to match the shared Qdrant collection's configured
        # size — same operational trap as GLM. Pick a dedicated
        # EMBEDDING_PROVIDER instead of routing embeddings through Ollama.
        raise EmbeddingsNotSupportedError(
            "Ollama embedding dimensions vary by local model and are not wired to the "
            "memory collection; set EMBEDDING_PROVIDER to a provider with a fixed, "
            "known dimension (e.g. openai)."
        )
