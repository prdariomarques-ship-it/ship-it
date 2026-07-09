"""Base class shared by every Dario OS agent.

An agent is a system prompt plus optional domain tools. The base class handles
memory injection and the LLM call; subclasses declare identity and behaviour.
"""
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from services.openai_service import openai_service


class BaseAgent(ABC):
    """Prompt-driven agent with permanent-memory context."""

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

    def _build_context(self, memories: list[dict]) -> str:
        if not memories:
            return ""
        lines = [f"- ({memory['source']}) {memory['content']}" for memory in memories]
        return "\n\nMemórias relevantes sobre o assunto:\n" + "\n".join(lines)

    async def run(self, db: AsyncSession, message: str, memories: list[dict] | None = None) -> str:
        del db  # subclasses with database tools use it; the base agent is prompt-only
        prompt = self.system_prompt + self._build_context(memories or [])
        return await openai_service.complete(system_prompt=prompt, user_message=message)
