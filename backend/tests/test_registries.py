"""Tool Registry and Agent Registry: self-registration and auto-discovery."""
import pytest

from agents.registry import DuplicateAgentError, UnknownAgentError, get_agent, list_agents, register_agent
from agents.tools.base import Tool
from agents.tools.registry import DuplicateToolError, get_tool, list_tools


# --- Tool Registry ------------------------------------------------------------
def test_every_agent_tool_is_discoverable_in_the_registry():
    # Constructing any agent (via list_agents, which triggers discovery) imports
    # every *_agent.py module, which imports its tools, which self-register.
    list_agents()
    names = {tool.name for tool in list_tools()}
    assert "create_task" in names
    assert "find_contact" in names
    assert "update_contact_preference" in names


def test_get_tool_returns_none_for_unknown_name():
    assert get_tool("does_not_exist") is None


async def _dummy_handler(context, **kwargs) -> str:
    return "{}"


def test_registering_the_same_tool_object_twice_is_a_no_op():
    from agents.tools.registry import register_tool

    tool = Tool(name="test_dummy_tool_a", description="d", handler=_dummy_handler)
    register_tool(tool)  # re-registering the exact same instance must not raise
    assert get_tool("test_dummy_tool_a") is tool


def test_registering_a_different_tool_with_the_same_name_raises():
    Tool(name="test_dummy_tool_b", description="first", handler=_dummy_handler)
    with pytest.raises(DuplicateToolError):
        Tool(name="test_dummy_tool_b", description="second", handler=_dummy_handler)


# --- Agent Registry -------------------------------------------------------------
def test_all_five_business_agents_are_auto_discovered():
    names = {agent.name for agent in list_agents()}
    assert names == {"personal", "church", "store", "content", "assistant"}


def test_get_agent_unknown_name_raises():
    with pytest.raises(UnknownAgentError):
        get_agent("does_not_exist")


def test_register_agent_installs_a_new_agent_with_zero_core_changes():
    """This is the whole point of item 8: dropping in a class + decorator is enough."""
    from agents.base import BaseAgent

    @register_agent
    class _PluginAgent(BaseAgent):
        @property
        def name(self) -> str:
            return "plugin_test_agent"

        @property
        def description(self) -> str:
            return "installed purely via the decorator, no registry.py edit"

        @property
        def system_prompt(self) -> str:
            return "prompt"

    agent = get_agent("plugin_test_agent")
    assert agent.description.startswith("installed purely")
    assert any(a.name == "plugin_test_agent" for a in list_agents())


def test_register_agent_rejects_duplicate_name_from_a_different_class():
    from agents.base import BaseAgent

    @register_agent
    class _First(BaseAgent):
        @property
        def name(self) -> str:
            return "plugin_dup_test"

        @property
        def description(self) -> str:
            return "first"

        @property
        def system_prompt(self) -> str:
            return "p"

    with pytest.raises(DuplicateAgentError):

        @register_agent
        class _Second(BaseAgent):
            @property
            def name(self) -> str:
                return "plugin_dup_test"

            @property
            def description(self) -> str:
                return "second"

            @property
            def system_prompt(self) -> str:
                return "p"
