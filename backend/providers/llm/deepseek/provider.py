"""DeepSeek LLM provider.

DeepSeek exposes an OpenAI-compatible API, so this provider reuses the OpenAI
implementation pointed at the DeepSeek endpoint — same trick as GLM.
"""

from providers.llm.base import EmbeddingsNotSupportedError
from providers.llm.openai.provider import OpenAIProvider
from utils.config import get_settings


class DeepSeekProvider(OpenAIProvider):
    name = "deepseek"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        super().__init__(
            api_key=api_key if api_key is not None else settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=model or settings.deepseek_model,
        )

    async def embed(self, text: str) -> list[float]:
        # DeepSeek has no embeddings API.
        raise EmbeddingsNotSupportedError(
            "DeepSeek has no embeddings API; "
            "set EMBEDDING_PROVIDER=openai (or another compatible provider)."
        )
