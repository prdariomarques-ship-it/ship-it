"""Tool Registry: every Tool instance registers itself the moment it's created.

Tool modules already declare their tools as module-level singletons
(`create_task_tool = Tool(...)`); this registry just observes that
construction, so existing tool files needed zero changes to become
discoverable. New tools work the same way — define a `Tool(...)`, import its
module once (agents already do, to build their `tools` list), and it shows up
in `list_tools()` / `get_tool()` automatically.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.tools.base import Tool

_TOOLS: dict[str, "Tool"] = {}


class DuplicateToolError(ValueError):
    pass


def register_tool(tool: "Tool") -> None:
    existing = _TOOLS.get(tool.name)
    if existing is not None and existing is not tool:
        raise DuplicateToolError(f"Tool {tool.name!r} is already registered")
    _TOOLS[tool.name] = tool


def get_tool(name: str) -> "Tool | None":
    return _TOOLS.get(name)


def list_tools() -> list["Tool"]:
    return list(_TOOLS.values())
