"""AI Orchestrator: the single entry point for running an agent conversation.

Chat (`/api/chat`), the direct `/api/agents/{name}/run` endpoint, and the
WhatsApp automatic reply (`jobs/handlers.py::process_inbound_whatsapp_message`)
all go through here instead of reaching into `agents.registry` / `BaseAgent`
directly. Centralizing the flow means:

- **Agent selection is one decision point.** Today it's just the explicit
  `agent_name` (defaulting to `assistant`); swapping in an intent classifier
  or a Goal Planner later (Phase 4) is a change to this one method, not to
  every caller.
- **Lifecycle events always fire**, regardless of which caller triggered the
  run — `agent.selected`, `agent.replied` and `agent.failed` go out on the
  Event Bus so the future AI Console (or anything else) can observe agent
  activity without the orchestrator knowing who's listening.
- **Memory is fetched exactly once**, by `BaseAgent.run` itself. Callers used
  to duplicate that lookup (chat/service.py pre-Phase-3) just to compute a
  count for the response; `AgentResult.memories_used` now carries it instead.
- **Every run is bounded and measured.** A hung LLM call or a runaway tool
  loop can't hang the caller forever (`AGENT_RUN_TIMEOUT_SECONDS`), and every
  run's duration, token usage, estimated cost and tool calls are recorded
  here — one place, so no caller has to remember to instrument itself.

This is deliberately thin: it does not decide *how* an agent thinks (that's
`BaseAgent`/`Planner`/`AgentExecutor`) or *what* memory to use (that's
`MemoryManager`). It only coordinates "which agent, with which events and
metrics."
"""
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from agents.executor import AgentResult
from agents.registry import get_agent
from events.bus import event_bus
from models.user import User
from observability.metrics import record_agent_run, record_tool_call
from providers.llm.base import ChatMessage, estimate_cost_usd
from providers.llm.factory import get_llm_provider
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class AgentTimeoutError(RuntimeError):
    """Raised when an agent run exceeds AGENT_RUN_TIMEOUT_SECONDS."""


class AIOrchestrator:
    async def run(
        self,
        db: AsyncSession,
        user: User,
        message: str,
        agent_name: str = "assistant",
        contact_id: int | None = None,
        memories: list[dict] | None = None,
        history: list[ChatMessage] | None = None,
    ) -> AgentResult:
        """Select the agent (raises UnknownAgentError if the name is invalid),
        run it under a timeout, and publish lifecycle events + metrics.

        `memories`/`history` are optional pre-fetched context (used by
        `orchestrator.pipeline.CognitivePipeline`, which already queried
        memory once for the whole plan and would otherwise duplicate that
        lookup per step); left `None`, `agent.run` fetches memory itself
        exactly as before — existing callers (chat, `/api/agents/*/run`) are
        unaffected.
        """
        agent = get_agent(agent_name)
        provider_name = get_llm_provider().name
        await event_bus.publish(
            "agent.selected",
            {"agent": agent.name, "contact_id": contact_id, "user_id": user.id},
        )

        timeout = get_settings().agent_run_timeout_seconds
        try:
            result = await asyncio.wait_for(
                agent.run(
                    db=db,
                    user=user,
                    message=message,
                    contact_id=contact_id,
                    memories=memories,
                    history=history,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            record_agent_run(agent=agent.name, provider=provider_name, status="timeout", duration_seconds=timeout)
            await event_bus.publish(
                "agent.failed",
                {"agent": agent.name, "contact_id": contact_id, "user_id": user.id, "reason": "timeout"},
            )
            raise AgentTimeoutError(f"Agent {agent.name!r} exceeded {timeout}s") from exc

        cost_usd = estimate_cost_usd(provider_name, result.usage)
        record_agent_run(
            agent=agent.name,
            provider=provider_name,
            status="ok",
            duration_seconds=result.duration_ms / 1000,
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            cost_usd=cost_usd,
        )
        for step in result.steps:
            record_tool_call(step.tool, status=step.status)

        await event_bus.publish(
            "agent.replied",
            {
                "agent": agent.name,
                "contact_id": contact_id,
                "user_id": user.id,
                "provider": provider_name,
                "tool_calls": len(result.steps),
                "memories_used": result.memories_used,
                "duration_ms": result.duration_ms,
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "cost_usd": cost_usd,
            },
        )
        return result


ai_orchestrator = AIOrchestrator()
