"""Priority Engine: how urgently a message needs a response.

Same shape as the Intent Engine — an independent component, LLM decision as
the primary path, keyword heuristic as the degrade path — plus one extra,
synchronous entry point (`quick_priority_hint`) used at webhook time, before
any job exists to run the full pipeline in. It never calls an LLM (the
webhook hot path must stay fast, same principle that already keeps embedding
off the request path — see `ContactMemoryService.record_interaction`): it
reuses the same heuristic keyword table as the fallback, just exposed
directly, and lets urgent messages jump the job queue via a shorter
`delay_seconds` when enqueued (`webhooks/router.py`).
"""

from enum import Enum

from pydantic import BaseModel

from orchestrator.intent import Intent, IntentResult
from providers.llm.base import ChatMessage, LLMProvider, ToolSpec
from providers.llm.factory import get_llm_provider


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class PriorityResult(BaseModel):
    level: Priority
    reason: str = ""


_PRIORITY_VALUES = [priority.value for priority in Priority]

_PRIORITY_TOOL = ToolSpec(
    name="classify_priority",
    description="Registra o nível de prioridade da mensagem do usuário e uma justificativa curta.",
    parameters={
        "type": "object",
        "properties": {
            "level": {"type": "string", "enum": _PRIORITY_VALUES},
            "reason": {"type": "string"},
        },
        "required": ["level"],
    },
)

_PRIORITY_SYSTEM_PROMPT = (
    "Você é o mecanismo de priorização do Dario OS. A intenção já identificada "
    "para esta mensagem é '{intent}'. Classifique a urgência chamando "
    "classify_priority com um nível ({levels}) e uma justificativa curta. "
    "Não responda em texto livre, apenas chame a ferramenta."
)

_URGENT_KEYWORDS = (
    "urgente",
    "urgência",
    "urgencia",
    "emergência",
    "emergencia",
    "socorro",
    "agora mesmo",
    "imediato",
    "imediatamente",
)
_HIGH_KEYWORDS = (
    "hoje",
    "o quanto antes",
    "o mais rápido possível",
    "o mais rapido possivel",
    "importante",
)
_LOW_INTENTS = (Intent.GREETING, Intent.SMALL_TALK)


def quick_priority_hint(message: str) -> Priority:
    """Fast, non-LLM priority guess for the webhook hot path — never blocks
    on a model call. The full PriorityEngine refines this once the message
    reaches the Cognitive Pipeline; this is only used to order the job queue."""
    lowered = message.lower()
    if any(keyword in lowered for keyword in _URGENT_KEYWORDS):
        return Priority.URGENT
    if any(keyword in lowered for keyword in _HIGH_KEYWORDS):
        return Priority.HIGH
    return Priority.NORMAL


class PriorityEngine:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self._llm = llm

    def _llm_provider(self) -> LLMProvider:
        return self._llm or get_llm_provider()

    async def classify(self, message: str, intent: IntentResult) -> PriorityResult:
        try:
            result = await self._llm_provider().chat(
                [
                    ChatMessage(
                        role="system",
                        content=_PRIORITY_SYSTEM_PROMPT.format(
                            intent=intent.top.value, levels=", ".join(_PRIORITY_VALUES)
                        ),
                    ),
                    ChatMessage(role="user", content=message),
                ],
                tools=[_PRIORITY_TOOL],
            )
        except Exception:  # noqa: BLE001 - classification is best-effort, never blocks the pipeline
            return self._fallback(message, intent)
        call = next(
            (c for c in result.tool_calls if c.name == "classify_priority"), None
        )
        if call is None or call.arguments.get("level") not in _PRIORITY_VALUES:
            return self._fallback(message, intent)
        return PriorityResult(
            level=Priority(call.arguments["level"]),
            reason=str(call.arguments.get("reason", "")),
        )

    def _fallback(self, message: str, intent: IntentResult) -> PriorityResult:
        hint = quick_priority_hint(message)
        if hint is Priority.URGENT:
            return PriorityResult(
                level=Priority.URGENT, reason="palavra-chave de urgência detectada"
            )
        if hint is Priority.HIGH:
            return PriorityResult(
                level=Priority.HIGH, reason="palavra-chave de prioridade alta detectada"
            )
        if intent.top == Intent.ADMIN_COMMAND:
            return PriorityResult(level=Priority.HIGH, reason="comando administrativo")
        if intent.top in _LOW_INTENTS:
            return PriorityResult(level=Priority.LOW, reason="conversa casual")
        return PriorityResult(level=Priority.NORMAL, reason="prioridade padrão")
