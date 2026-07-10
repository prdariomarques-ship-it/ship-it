"""Executor: runs the plan → act → observe loop with function calling.

Each iteration asks the LLM for the next step; requested tool calls are
executed against the application services and their results fed back, until
the model produces a final answer (or the iteration budget runs out).
"""
import time

from pydantic import BaseModel, Field

from agents.tools.base import Tool, ToolContext
from providers.llm.base import ChatMessage, LLMProvider, TokenUsage
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class ExecutedStep(BaseModel):
    tool: str
    arguments: dict
    result: str
    duration_ms: float = 0.0


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

    async def run(self, messages: list[ChatMessage], context: ToolContext) -> AgentResult:
        started = time.perf_counter()
        specs = [tool.spec() for tool in self._tools.values()] or None
        steps: list[ExecutedStep] = []
        usage = TokenUsage()

        for _ in range(self._max_iterations):
            result = await self._llm.chat(messages, tools=specs)
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
                    ExecutedStep(tool=call.name, arguments=call.arguments, result=output, duration_ms=duration_ms)
                )
                messages.append(ChatMessage(role="tool", content=output, tool_call_id=call.id))

        # Iteration budget exhausted: ask for a final answer without tools.
        final = await self._llm.chat(messages)
        usage = usage + final.usage
        return AgentResult(
            reply=final.content, steps=steps, usage=usage, duration_ms=(time.perf_counter() - started) * 1000
        )
