"""OpenAI (and OpenAI-compatible) LLM provider."""
import json

from openai import AsyncOpenAI

from providers.llm.base import (
    STUB_REPLY,
    ChatMessage,
    LLMProvider,
    LLMResult,
    ToolCallRequest,
    ToolSpec,
)
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        embedding_model: str | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._base_url = base_url if base_url is not None else (settings.openai_base_url or None)
        self._model = model or settings.openai_model
        self._embedding_model = embedding_model or settings.openai_embedding_model
        self._dimensions = settings.embedding_dimensions
        self._client: AsyncOpenAI | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def _to_openai_messages(self, messages: list[ChatMessage]) -> list[dict]:
        converted: list[dict] = []
        for message in messages:
            if message.role == "tool":
                converted.append(
                    {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
                )
            elif message.role == "assistant" and message.tool_calls:
                converted.append(
                    {
                        "role": "assistant",
                        "content": message.content or None,
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": json.dumps(call.arguments),
                                },
                            }
                            for call in message.tool_calls
                        ],
                    }
                )
            else:
                converted.append({"role": message.role, "content": message.content})
        return converted

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None) -> LLMResult:
        if not self.enabled:
            logger.warning("OpenAI provider not configured; returning stub response")
            return LLMResult(content=STUB_REPLY)

        kwargs: dict = {"model": self._model, "messages": self._to_openai_messages(messages)}
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]

        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0].message

        tool_calls = [
            ToolCallRequest(
                id=call.id,
                name=call.function.name,
                arguments=json.loads(call.function.arguments or "{}"),
            )
            for call in (choice.tool_calls or [])
        ]
        return LLMResult(content=choice.content or "", tool_calls=tool_calls)

    async def embed(self, text: str) -> list[float]:
        if not self.enabled:
            return [0.0] * self._dimensions
        response = await self.client.embeddings.create(model=self._embedding_model, input=text)
        return response.data[0].embedding
