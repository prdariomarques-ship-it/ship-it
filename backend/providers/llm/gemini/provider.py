"""Google Gemini provider — plain REST via httpx (already a dependency for the
WhatsApp providers), so supporting a fifth vendor added zero new dependencies.

Gemini's wire format differs from the two families already supported:
- turns are "user"/"model" (not "system"/"user"/"assistant"/"tool"); the
  system prompt is a top-level `systemInstruction`, and tool results go back
  as a "user" turn carrying a `functionResponse` part — the same shape
  Anthropic uses for tool results, different from OpenAI's dedicated role.
- function calls have no id: Gemini matches a tool result to a call by
  `name` alone. Our neutral `ToolCallRequest` needs an id (OpenAI/Anthropic
  both provide one), so this provider synthesizes one per call and keeps a
  local id->name map while converting a conversation, so a later
  `role="tool"` message can be turned back into a correctly named
  `functionResponse`.
"""

from typing import Any

import httpx

from providers.llm.base import (
    STUB_REPLY,
    ChatMessage,
    LLMProvider,
    LLMResult,
    ToolCallRequest,
    ToolSpec,
    TokenUsage,
)
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        embedding_model: str | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.gemini_api_key
        self._base_url = (base_url or settings.gemini_base_url).rstrip("/")
        self._model = model or settings.gemini_model
        self._embedding_model = embedding_model or settings.gemini_embedding_model
        self._timeout = settings.llm_request_timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def _to_gemini_contents(
        self, messages: list[ChatMessage]
    ) -> tuple[dict | None, list[dict]]:
        system_instruction = None
        contents: list[dict] = []
        call_id_to_name: dict[str, str] = {}

        for message in messages:
            if message.role == "system":
                system_instruction = {"parts": [{"text": message.content}]}
                continue

            if message.role == "tool":
                name = call_id_to_name.get(message.tool_call_id or "", "unknown_tool")
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": name,
                                    "response": {"result": message.content},
                                }
                            }
                        ],
                    }
                )
                continue

            if message.role == "assistant" and message.tool_calls:
                parts: list[dict[str, Any]] = (
                    [{"text": message.content}] if message.content else []
                )
                for call in message.tool_calls:
                    call_id_to_name[call.id] = call.name
                    parts.append(
                        {"functionCall": {"name": call.name, "args": call.arguments}}
                    )
                contents.append({"role": "model", "parts": parts})
                continue

            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})

        return system_instruction, contents

    async def chat(
        self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None
    ) -> LLMResult:
        if not self.enabled:
            logger.warning("Gemini provider not configured; returning stub response")
            return LLMResult(content=STUB_REPLY)

        system_instruction, contents = self._to_gemini_contents(messages)
        body: dict = {"contents": contents}
        if system_instruction:
            body["systemInstruction"] = system_instruction
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        }
                        for tool in tools
                    ]
                }
            ]

        url = f"{self._base_url}/models/{self._model}:generateContent"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, params={"key": self._api_key}, json=body)
            response.raise_for_status()
            data = response.json()

        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        for index, part in enumerate(parts):
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                call = part["functionCall"]
                tool_calls.append(
                    ToolCallRequest(
                        id=f"gemini_call_{index}",
                        name=call["name"],
                        arguments=dict(call.get("args", {})),
                    )
                )

        usage_meta = data.get("usageMetadata", {})
        usage = TokenUsage(
            prompt_tokens=usage_meta.get("promptTokenCount", 0),
            completion_tokens=usage_meta.get("candidatesTokenCount", 0),
        )
        return LLMResult(
            content="".join(text_parts), tool_calls=tool_calls, usage=usage
        )

    async def embed(self, text: str) -> list[float]:
        if not self.enabled:
            return [0.0] * get_settings().embedding_dimensions

        url = f"{self._base_url}/models/{self._embedding_model}:embedContent"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                url,
                params={"key": self._api_key},
                json={"content": {"parts": [{"text": text}]}},
            )
            response.raise_for_status()
            data = response.json()
        return list(data.get("embedding", {}).get("values", []))
