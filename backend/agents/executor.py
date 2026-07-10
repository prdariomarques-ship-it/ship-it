"""Executor: runs the plan → act → observe loop with function calling.

Each iteration asks the LLM for the next step; requested tool calls are
executed against the application services and their results fed back, until
the model produces a final answer (or the iteration budget runs out).
"""
import json
import time

from pydantic import BaseModel, Field

from agents.tools.base import Tool, ToolContext
from providers.llm.base import ChatMessage, LLMProvider, TokenUsage, ToolSpec
from providers.llm.factory import get_fallback_llm_provider
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


def is_tool_error(result: str) -> bool:
    """True when a tool's own JSON result envelope reports an error (see
    `agents.tools.base.Tool.run`, which always catches exceptions into
    `{"error": ...}` rather than propagating them to the executor)."""
    try:
        parsed = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(parsed, dict) and "error" in parsed


class ExecutedStep(BaseModel):
    tool: str
    arguments: dict
    result: str
    duration_ms: float = 0.0
    status: str = "ok"  # "ok" | "error" — derived from the tool's own result envelope
    reason: str = ""  # the model's own words alongside the tool call, when it gave any


class AgentResult(BaseModel):
    reply: str
    steps: list[ExecutedStep] = []
    memories_used: int = 0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    duration_ms: float = 0.0


class AgentExecutor:
    def __init__(self, llm: LLMProvider, tools: list[Tool], max_iterations: int | None = None) -> None:
        self._llm = llm
        self._tools = {tool.name: tool for tool in tools}
        self._max_iterations = max_iterations or get_settings().agent_max_iterations

    async def _chat_with_fallback(
        self, messages: list[ChatMessage], tools: list[ToolSpec] | None = None
    ):
        """Automatic provider switch: a raised exception from the primary
        LLM_PROVIDER (network outage, provider-side error, expired key —
        distinct from a provider degrading gracefully to STUB_REPLY, which
        never raises) triggers one retry against LLM_FALLBACK_PROVIDER, if
        configured. Unconfigured (the default), or the fallback fails too:
        the exception propagates exactly as before this existed."""
        try:
            return await self._llm.chat(messages, tools=tools)
        except Exception as exc:  # noqa: BLE001 - this is the failover trigger, not a swallow
            fallback = get_fallback_llm_provider()
            if fallback is None or fallback.name == self._llm.name:
                raise
            logger.warning(
                "LLM provider %s failed (%s); switching to fallback provider %s",
                self._llm.name, exc, fallback.name,
            )
            self._llm = fallback
            return await self._llm.chat(messages, tools=tools)

    async def run(self, messages: list[ChatMessage], context: ToolContext) -> AgentResult:
        started = time.perf_counter()
        specs = [tool.spec() for tool in self._tools.values()] or None
        steps: list[ExecutedStep] = []
        usage = TokenUsage()

        for _ in range(self._max_iterations):
            result = await self._chat_with_fallback(messages, tools=specs)
            usage = usage + result.usage

            if not result.tool_calls:
                return AgentResult(
                    reply=result.content,
                    steps=steps,
                    usage=usage,
                    duration_ms=(time.perf_counter() - started) * 1000,
                )

            messages.append(
                ChatMessage(role="assistant", content=result.content, tool_calls=result.tool_calls)
            )
            reason = result.content.strip() if result.content else ""
            for call in result.tool_calls:
                tool = self._tools.get(call.name)
                step_started = time.perf_counter()
                if tool is None:
                    output = f'{{"error": "Unknown tool: {call.name}"}}'
                else:
                    output = await tool.run(context, call.arguments)
                duration_ms = (time.perf_counter() - step_started) * 1000
                # Debug level: arguments/results may contain user data (PII).
                logger.debug("Agent tool %s(%s) -> %.200s", call.name, call.arguments, output)
                steps.append(
                    ExecutedStep(
                        tool=call.name,
                        arguments=call.arguments,
                        result=output,
                        duration_ms=duration_ms,
                        status="error" if is_tool_error(output) else "ok",
                        reason=reason,
                    )
                )
                messages.append(ChatMessage(role="tool", content=output, tool_call_id=call.id))

        # Iteration budget exhausted: ask for a final answer without tools.
        final = await self._chat_with_fallback(messages)
        usage = usage + final.usage
        return AgentResult(
            reply=final.content, steps=steps, usage=usage, duration_ms=(time.perf_counter() - started) * 1000
        )
