"""Darius Twin: first-person impersonation agent for Dário's personal
WhatsApp number.

Every other agent in this registry (`personal`, `assistant`, `store`,
`church`, `content`) answers *as an assistant*, visibly automated, on
Dário's behalf. This one is different by design -- see
`agents/prompts/darius_twin_manual.md` ("Instrução de identidade"): it
answers *as* Dário, first person, and must never disclose that it's
automated. That is exactly why it's the only agent in this codebase
gated by `orchestrator.twin_risk_gate.TwinRiskGate` before it's allowed
to speak -- see that module's docstring for why an impersonation agent
carries a materially higher failure cost than a disclosed-assistant one.

Reachability for *automatic* WhatsApp replies is scoped by
`WHATSAPP_ENABLED_AGENTS` (`utils.config.Settings`, consumed by
`orchestrator.planning._enabled_agent_names`) -- each WhatsApp number is
its own docker compose deployment sharing the same image/Agent Registry
(see that setting's docstring). This agent must be added to
`WHATSAPP_ENABLED_AGENTS` only on Dário's own personal-number deployment,
never on the business/store deployment. It remains directly invocable
regardless of that setting via the dashboard or
`POST /api/agents/twin/run` -- the scope only narrows automatic routing.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import BaseAgent
from agents.executor import AgentResult
from agents.prompts.loader import load_prompt
from agents.registry import register_agent
from agents.tools.base import Tool
from agents.tools.communication import search_memory_tool, store_memory_tool
from models.user import User
from orchestrator.twin_risk_gate import ESCALATION_MESSAGE, twin_risk_gate
from providers.llm.base import ChatMessage
from utils.logging import get_logger

logger = get_logger(__name__)


@register_agent
class DariusTwinAgent(BaseAgent):
    """Responde no WhatsApp pessoal do Dário em primeira pessoa, como se
    fosse ele mesmo -- ver `agents/prompts/darius_twin_manual.md`."""

    @property
    def name(self) -> str:
        return "twin"

    @property
    def description(self) -> str:
        return (
            "Twin digital do Dário: responde em primeira pessoa no WhatsApp "
            "pessoal dele (visão pastoral, investimentos, filosofia aplicada). "
            "Uso restrito ao número pessoal -- ver WHATSAPP_ENABLED_AGENTS."
        )

    @property
    def system_prompt(self) -> str:
        return load_prompt("darius_twin_manual.md")

    @property
    def tools(self) -> list[Tool]:
        # Deliberately minimal -- the manual's scope is conversation
        # (pastoral, investimentos, filosofia), not the operational tool
        # surface `assistant`/`store` need (agenda, pedidos, e-mail...).
        # Anything beyond memory would widen what an impersonation agent
        # can *do* in Dário's name, on top of what it can *say* -- a
        # second axis of risk this agent doesn't need to take on.
        return [search_memory_tool, store_memory_tool]

    async def run(
        self,
        db: AsyncSession,
        user: User,
        message: str,
        contact_id: int | None = None,
        memories: list[dict] | None = None,
        history: list[ChatMessage] | None = None,
    ) -> AgentResult:
        assessment = await twin_risk_gate.assess(message)
        if assessment.should_escalate:
            logger.warning(
                "Twin risk gate escalated (contact_id=%s, category=%s): %s",
                contact_id,
                assessment.category.value,
                assessment.reason,
            )
            return AgentResult(reply=ESCALATION_MESSAGE)
        return await super().run(
            db,
            user,
            message,
            contact_id=contact_id,
            memories=memories,
            history=history,
        )
