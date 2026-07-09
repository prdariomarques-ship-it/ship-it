"""Registry with every available agent, keyed by name."""
from agents.base import BaseAgent
from agents.church import ChurchAgent
from agents.content import ContentAgent
from agents.personal import PersonalAgent
from agents.store import StoreAgent
from agents.whatsapp import WhatsAppAgent


class UnknownAgentError(KeyError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown agent: {name!r}")
        self.name = name

    def __str__(self) -> str:
        return f"Unknown agent: {self.name!r}"


_AGENTS: dict[str, BaseAgent] = {
    agent.name: agent
    for agent in (PersonalAgent(), WhatsAppAgent(), ChurchAgent(), StoreAgent(), ContentAgent())
}


def get_agent(name: str) -> BaseAgent:
    try:
        return _AGENTS[name]
    except KeyError:
        raise UnknownAgentError(name) from None


def list_agents() -> list[BaseAgent]:
    return list(_AGENTS.values())
