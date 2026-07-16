"""Cognitive Planner: decides *what to do*, never *how to do it*.

Distinct from `agents.planner.Planner` (which only assembles a message list
for one agent call) — this Planner works one level up: given the user's
message plus the intent/priority already classified, it decides how many
steps the request needs, which registered agent handles each one, and
whether execution should pause for human confirmation first. It never calls
a tool itself (rule: tool selection only ever happens through the Tool
Registry, inside `AgentExecutor`) — a `Plan` is pure data; something else
(`orchestrator.pipeline.CognitivePipeline`) executes it.

Primary decision path: one LLM function call (`create_plan`) that can name
any currently-registered agent — the list comes from the Agent Registry at
call time, so a new agent installed by folder convention (Fase 3) is
automatically plannable, no change needed here. Degrade path (no LLM key,
unparseable response): a single-step plan for the *original* message, agent
chosen by a small intent→agent hint table, falling back to `assistant` —
this exactly reproduces the pre-Fase-4.2 behaviour of the WhatsApp auto-reply
handler, so existing single-step flows are unaffected when the model is
unavailable.
"""

from enum import Enum

from pydantic import BaseModel

from agents.registry import list_agents
from orchestrator.intent import Intent, IntentResult
from orchestrator.priority import PriorityResult
from providers.llm.base import ChatMessage, LLMProvider, ToolSpec
from providers.llm.factory import get_llm_provider

_MAX_PLAN_STEPS = 5

_INTENT_AGENT_HINTS: dict[Intent, str] = {
    Intent.SCHEDULE: "personal",
    Intent.APPOINTMENT: "personal",
    Intent.REMINDER: "personal",
    Intent.TASK: "personal",
    Intent.RESEARCH: "content",
    Intent.WEB_SEARCH: "content",
    Intent.DOCUMENT: "content",
    Intent.STORE: "store",
    Intent.CHURCH: "church",
}


class PlanStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(BaseModel):
    objective: str
    agent: str
    depends_on: list[int] = []
    status: PlanStepStatus = PlanStepStatus.PENDING
    result: str | None = None


class Plan(BaseModel):
    steps: list[PlanStep]
    needs_confirmation: bool = False
    reasoning: str = ""
    # How confident the planner is that this decomposition (step count, agent
    # per step, dependencies) actually matches what the user needs -- distinct
    # from Intent/Priority confidence, which score the *classification*, not
    # the *plan* built from it. Low on the fallback path (0.3, see
    # _fallback_plan) since a keyword-hint single-step plan is a degraded
    # guess, never a reasoned decision; on the primary path it comes straight
    # from the model's own self-reported confidence in the create_plan call.
    confidence: float = 1.0


def _fallback_agent_for_intent(intent: Intent, agent_names: list[str]) -> str:
    preferred = _INTENT_AGENT_HINTS.get(intent)
    if preferred in agent_names:
        return preferred
    return "assistant" if "assistant" in agent_names else agent_names[0]


def _build_plan_tool(agent_names: list[str]) -> ToolSpec:
    return ToolSpec(
        name="create_plan",
        description=(
            "Registra o plano de execução para atender ao pedido do usuário. "
            "Divida em múltiplas etapas apenas quando o pedido realmente exigir "
            "mais de uma ação; um pedido simples deve virar um plano de uma etapa só."
        ),
        parameters={
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": _MAX_PLAN_STEPS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "objective": {
                                "type": "string",
                                "description": "O que esta etapa deve realizar, em linguagem natural.",
                            },
                            "agent": {"type": "string", "enum": agent_names},
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Índices (0-based) de etapas anteriores que precisam terminar antes desta.",
                            },
                        },
                        "required": ["objective", "agent"],
                    },
                },
                "needs_confirmation": {
                    "type": "boolean",
                    "description": "true se o plano deve ser confirmado pelo usuário antes de ser executado.",
                },
                "reasoning": {"type": "string"},
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Quão confiante você está de que este plano (número de etapas, agente escolhido, dependências) atende bem ao pedido.",
                },
            },
            "required": ["steps"],
        },
    )


def _plan_system_prompt(
    agent_names: list[str], intent: IntentResult, priority: PriorityResult
) -> str:
    return (
        "Você é o Planejador Cognitivo do Dario OS. Agentes disponíveis: "
        + ", ".join(agent_names)
        + f". Intenção identificada: {intent.top.value}. Prioridade: {priority.level.value}. "
        "Chame create_plan com uma ou mais etapas. Só peça confirmação "
        "(needs_confirmation=true) quando o pedido for ambíguo ou tiver "
        "consequências relevantes (ex: cancelar algo, enviar mensagem em massa)."
    )


class CognitivePlanner:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self._llm = llm

    def _llm_provider(self) -> LLMProvider:
        return self._llm or get_llm_provider()

    async def create_plan(
        self, message: str, intent: IntentResult, priority: PriorityResult
    ) -> Plan:
        agent_names = [agent.name for agent in list_agents()]
        if not agent_names:
            return Plan(steps=[])

        try:
            result = await self._llm_provider().chat(
                [
                    ChatMessage(
                        role="system",
                        content=_plan_system_prompt(agent_names, intent, priority),
                    ),
                    ChatMessage(role="user", content=message),
                ],
                tools=[_build_plan_tool(agent_names)],
            )
        except Exception:  # noqa: BLE001 - planning is best-effort, never blocks the pipeline
            return self._fallback_plan(message, intent, agent_names)
        call = next((c for c in result.tool_calls if c.name == "create_plan"), None)
        if call is None:
            return self._fallback_plan(message, intent, agent_names)

        steps: list[PlanStep] = []
        for raw in (call.arguments.get("steps") or [])[:_MAX_PLAN_STEPS]:
            agent = raw.get("agent")
            if agent not in agent_names:
                agent = _fallback_agent_for_intent(intent.top, agent_names)
            objective = str(raw.get("objective") or "").strip() or message
            depends_on = [
                int(d) for d in raw.get("depends_on", []) if isinstance(d, int)
            ]
            steps.append(
                PlanStep(objective=objective, agent=agent, depends_on=depends_on)
            )

        if not steps:
            return self._fallback_plan(message, intent, agent_names)

        try:
            confidence = float(call.arguments.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        confidence = max(0.0, min(1.0, confidence))

        return Plan(
            steps=steps,
            needs_confirmation=bool(call.arguments.get("needs_confirmation", False)),
            reasoning=str(call.arguments.get("reasoning", "")),
            confidence=confidence,
        )

    def _fallback_plan(
        self, message: str, intent: IntentResult, agent_names: list[str]
    ) -> Plan:
        agent = _fallback_agent_for_intent(intent.top, agent_names)
        return Plan(
            steps=[PlanStep(objective=message, agent=agent)],
            reasoning="plano de contingência: LLM indisponível, agente escolhido por tabela intenção→agente",
            confidence=0.3,
        )
