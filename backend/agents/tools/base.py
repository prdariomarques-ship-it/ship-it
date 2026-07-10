"""Function-calling tool abstraction for agents.

A Tool couples an LLM-visible spec (name, description, JSON Schema) with an
async handler that runs against the application services. Handlers always
return a JSON string — that's what goes back to the model.
"""
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from providers.llm.base import ToolSpec


@dataclass
class ToolContext:
    """Everything a tool handler may need, injected by the executor.

    `contact_id` is the contact the current conversation is scoped to (set by
    `BaseAgent.run`, sourced from application code — the webhook/DB layer,
    never from the LLM). Tools that reach across contacts (sending a WhatsApp
    message, looking up a contact) use it to enforce that a conversation can
    only ever act on its own contact; `None` means the call isn't bound to a
    specific conversation (e.g. an admin using the dashboard directly).
    """

    db: AsyncSession
    user: User
    contact_id: int | None = None


ToolHandler = Callable[..., Awaitable[str]]


@dataclass
class Tool:
    name: str
    description: str
    handler: ToolHandler  # async (context: ToolContext, **arguments) -> str
    parameters: dict = field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": []}
    )

    def __post_init__(self) -> None:
        # Self-registration: importing the module that defines a Tool is
        # enough for it to show up in the Tool Registry (GET /api/tools),
        # with no separate registration step for tool authors to remember.
        from agents.tools.registry import register_tool

        register_tool(self)

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters)

    async def run(self, context: ToolContext, arguments: dict) -> str:
        try:
            return await self.handler(context, **arguments)
        except TypeError as exc:  # bad/missing arguments from the model
            return json.dumps({"error": f"Invalid arguments: {exc}"})
        except Exception as exc:  # noqa: BLE001 - tool errors go back to the model
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})


def ok(**data: object) -> str:
    """JSON success envelope for tool results."""
    return json.dumps({"ok": True, **data}, ensure_ascii=False, default=str)
