"""Thin wrapper around the OpenAI API with graceful degradation when no key is set."""
from openai import AsyncOpenAI

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class OpenAIService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: AsyncOpenAI | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._settings.openai_api_key)

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self._settings.openai_api_key)
        return self._client

    async def complete(self, system_prompt: str, user_message: str, history: list[dict] | None = None) -> str:
        """Run a chat completion. Returns a stub answer when the API key is missing."""
        if not self.enabled:
            logger.warning("OPENAI_API_KEY not configured; returning stub response")
            return "[IA indisponível: configure OPENAI_API_KEY para ativar as respostas inteligentes]"

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": user_message})

        response = await self.client.chat.completions.create(
            model=self._settings.openai_model,
            messages=messages,  # type: ignore[arg-type]
        )
        return response.choices[0].message.content or ""

    async def embed(self, text: str) -> list[float]:
        """Return the embedding vector for a text (zeros when the API key is missing)."""
        if not self.enabled:
            return [0.0] * self._settings.embedding_dimensions

        response = await self.client.embeddings.create(
            model=self._settings.openai_embedding_model,
            input=text,
        )
        return response.data[0].embedding


openai_service = OpenAIService()
