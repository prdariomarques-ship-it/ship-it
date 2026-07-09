"""Registry with every available agent, keyed by name (Factory pattern)."""
from agents.assistant_agent import AssistantAgent
from agents.base import BaseAgent
from agents.church_agent import ChurchAgent
from agents.content_agent import ContentAgent
from agents.personal_agent import PersonalAgent
from agents.store_agent import StoreAgent


class UnknownAgentError(KeyError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown agent: {name!r}")
        self.name = name

    def __str__(self) -> str:
        return f"Unknown agent: {self.name!r}"


_AGENTS: dict[str, BaseAgent] = {
    agent.name: agent
    for agent in (PersonalAgent(), ChurchAgent(), StoreAgent(), ContentAgent(), AssistantAgent())
}


def get_agent(name: str) -> BaseAgent:
    try:
        return _AGENTS[name]
    except KeyError:
        raise UnknownAgentError(name) from None


def list_agents() -> list[BaseAgent]:
    return list(_AGENTS.values())
