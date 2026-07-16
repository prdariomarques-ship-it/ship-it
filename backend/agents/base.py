"""Base class shared by every Dario OS agent.

An agent = identity (name/description) + system prompt + tools + memory +
planner + executor. Subclasses declare identity and tool set; the run loop
(memory injection, planning, function calling) lives here.
"""

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from agents.executor import AgentExecutor, AgentResult
from agents.planner import Planner
from agents.tools.base import Tool, ToolContext
from memory.manager import memory_manager
from models.user import User
from providers.llm.base import ChatMessage
from providers.llm.factory import get_llm_provider
from utils.logging import get_logger

logger = get_logger(__name__)


class BaseAgent(ABC):
    """Prompt + tools agent with permanent memory and a plan/execute loop."""

    planner: Planner = Planner()

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique registry key, e.g. 'personal'."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable summary shown in the dashboard."""

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Instructions that define the agent's role."""

    @property
    def tools(self) -> list[Tool]:
        """Function-calling tools available to this agent."""
        return []

    async def run(
        self,
        db: AsyncSession,
        user: User,
        message: str,
        contact_id: int | None = None,
        memories: list[dict] | None = None,
        history: list[ChatMessage] | None = None,
    ) -> AgentResult:
        if memories is None:
            try:
                context_data = await memory_manager.build_agent_context(
                    message, contact_id
                )
                memories = context_data["memories"]
            except Exception as exc:  # noqa: BLE001 - memory is an enhancement, not a requirement
                logger.warning(
                    "Memory lookup skipped (vector store unavailable): %s", exc
                )
                memories = []

        messages = self.planner.build_messages(
            self.system_prompt, message, memories, history=history
        )
        executor = AgentExecutor(get_llm_provider(), self.tools)
        result = await executor.run(
            messages, ToolContext(db=db, user=user, contact_id=contact_id)
        )
        result.memories_used = len(memories)
        return result
