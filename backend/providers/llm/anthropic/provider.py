"""Anthropic (Claude) LLM provider."""
from anthropic import AsyncAnthropic

from providers.llm.base import (
    STUB_REPLY,
    ChatMessage,
    EmbeddingsNotSupportedError,
    LLMProvider,
    LLMResult,
    ToolCallRequest,
    ToolSpec,
    TokenUsage,
)
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.anthropic_api_key
        self._model = model or settings.anthropic_model
        self._max_tokens = settings.anthropic_max_tokens
        self._client: AsyncAnthropic | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    @property
    def client(self) -> AsyncAnthropic:
        if self._client is None:
            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    def _to_anthropic_messages(self, messages: list[ChatMessage]) -> tuple[str, list[dict]]:
        """Split the system prompt out and map tool traffic to content blocks."""
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        converted: list[dict] = []
        for message in messages:
            if message.role == "system":
                continue
            if message.role == "tool":
                converted.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.tool_call_id,
                                "content": message.content,
                            }
                        ],
                    }
                )
            elif message.role == "assistant" and message.tool_calls:
                blocks: list[dict] = []
                if message.content:
                    blocks.append({"type": "text", "text": message.content})
                blocks.extend(
                    {
                        "type": "tool_use",
                        "id": call.id,
                        "name": call.name,
                        "input": call.arguments,
                    }
                    for call in message.tool_calls
                )
                converted.append({"role": "assistant", "content": blocks})
            else:
                converted.append({"role": message.role, "content": message.content})
        return system, converted

    async def chat(self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None) -> LLMResult:
        if not self.enabled:
            logger.warning("Anthropic provider not configured; returning stub response")
            return LLMResult(content=STUB_REPLY)

        system, converted = self._to_anthropic_messages(messages)
        kwargs: dict = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": converted,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters,
                }
                for tool in tools
            ]

        response = await self.client.messages.create(**kwargs)

        content_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(id=block.id, name=block.name, arguments=dict(block.input or {}))
                )
        usage = TokenUsage(
            prompt_tokens=getattr(response.usage, "input_tokens", 0) or 0,
            completion_tokens=getattr(response.usage, "output_tokens", 0) or 0,
        ) if response.usage else TokenUsage()
        return LLMResult(content="".join(content_parts), tool_calls=tool_calls, usage=usage)

    async def embed(self, text: str) -> list[float]:
        raise EmbeddingsNotSupportedError(
            "Anthropic does not provide an embeddings API; "
            "set EMBEDDING_PROVIDER to a provider that does (e.g. openai)."
        )
