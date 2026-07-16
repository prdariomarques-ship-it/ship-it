"""GLM (Zhipu AI) LLM provider.

The Zhipu platform exposes an OpenAI-compatible API, so this provider reuses
the OpenAI implementation pointed at the GLM endpoint — same neutral contract,
different strategy configuration.
"""

from providers.llm.base import EmbeddingsNotSupportedError
from providers.llm.openai.provider import OpenAIProvider
from utils.config import get_settings


class GLMProvider(OpenAIProvider):
    name = "glm"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        super().__init__(
            api_key=api_key if api_key is not None else settings.glm_api_key,
            base_url=settings.glm_base_url,
            model=model or settings.glm_model,
            embedding_model="embedding-3",
        )

    async def embed(self, text: str) -> list[float]:
        # Zhipu's embedding-3 returns 2048 dims by default, which does not match
        # the configured Qdrant collection; keep memory on a dedicated provider.
        raise EmbeddingsNotSupportedError(
            "GLM embeddings are not wired to the memory collection; "
            "set EMBEDDING_PROVIDER=openai (or another compatible provider)."
        )
