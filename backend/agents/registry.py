"""Agent Registry: self-registration + auto-discovery (Factory pattern).

Installing a new agent is meant to be "add one file, nothing else":

    @register_agent
    class WeatherAgent(BaseAgent):
        @property
        def name(self) -> str: return "weather"
        ...

Any `*_agent.py` module dropped into this package is imported automatically
by `_discover()` (called once, lazily, on first registry access), so the
`@register_agent` decorator runs and the class is available through
`get_agent`/`list_agents` — no dict to edit, no import to add anywhere else.
"""
import importlib
import pkgutil
from typing import TypeVar

from agents.base import BaseAgent

AgentT = TypeVar("AgentT", bound=type[BaseAgent])

_AGENTS: dict[str, BaseAgent] = {}
_discovered = False


class UnknownAgentError(KeyError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown agent: {name!r}")
        self.name = name

    def __str__(self) -> str:
        return f"Unknown agent: {self.name!r}"


class DuplicateAgentError(ValueError):
    pass


def register_agent(agent_cls: AgentT) -> AgentT:
    """Class decorator: instantiate the agent once and register it by name."""
    instance = agent_cls()
    existing = _AGENTS.get(instance.name)
    if existing is not None and type(existing) is not agent_cls:
        raise DuplicateAgentError(
            f"Agent {instance.name!r} is already registered by {type(existing).__name__}"
        )
    _AGENTS[instance.name] = instance
    return agent_cls


def _discover() -> None:
    """Import every `*_agent.py` module in this package so its decorator runs."""
    global _discovered
    if _discovered:
        return
    _discovered = True

    import agents as agents_package

    for module_info in pkgutil.iter_modules(agents_package.__path__):
        if module_info.name.endswith("_agent"):
            importlib.import_module(f"agents.{module_info.name}")


def get_agent(name: str) -> BaseAgent:
    _discover()
    try:
        return _AGENTS[name]
    except KeyError:
        raise UnknownAgentError(name) from None


def list_agents() -> list[BaseAgent]:
    _discover()
    return list(_AGENTS.values())
