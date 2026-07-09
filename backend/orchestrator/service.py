"""AI Orchestrator: the single entry point for running an agent conversation.

Chat (`/api/chat`), the direct `/api/agents/{name}/run` endpoint, and any
future inbound channel all go through here instead of reaching into
`agents.registry` / `BaseAgent.run` directly. Centralizing the flow means:

- **Agent selection is one decision point.** Today it's just the explicit
  `agent_name` (defaulting to `assistant`); swapping in an intent classifier
  or a Goal Planner later (Phase 4) is a change to this one method, not to
  every caller.
- **Lifecycle events always fire**, regardless of which caller triggered the
  run — `agent.selected` and `agent.replied` go out on the Event Bus so the
  future AI Console (or anything else) can observe agent activity without
  the orchestrator knowing who's listening.
- **Memory is fetched exactly once**, by `BaseAgent.run` itself. Callers used
  to duplicate that lookup (chat/service.py pre-Phase-3) just to compute a
  count for the response; `AgentResult.memories_used` now carries it instead.

This is deliberately thin: it does not decide *how* an agent thinks (that's
`BaseAgent`/`Planner`/`AgentExecutor`) or *what* memory to use (that's
`MemoryManager`). It only coordinates "which agent, with which events."
"""
from sqlalchemy.ext.asyncio import AsyncSession

from agents.executor import AgentResult
from agents.registry import get_agent
from events.bus import event_bus
from models.user import User


class AIOrchestrator:
    async def run(
        self,
        db: AsyncSession,
        user: User,
        message: str,
        agent_name: str = "assistant",
        contact_id: int | None = None,
    ) -> AgentResult:
        """Select the agent (raises UnknownAgentError if the name is invalid),
        run it, and publish lifecycle events around the call."""
        agent = get_agent(agent_name)
        await event_bus.publish(
            "agent.selected",
            {"agent": agent.name, "contact_id": contact_id, "user_id": user.id},
        )

        result = await agent.run(db=db, user=user, message=message, contact_id=contact_id)

        await event_bus.publish(
            "agent.replied",
            {
                "agent": agent.name,
                "contact_id": contact_id,
                "user_id": user.id,
                "tool_calls": len(result.steps),
                "memories_used": result.memories_used,
            },
        )
        return result


ai_orchestrator = AIOrchestrator()
