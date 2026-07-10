"""Intent Engine: decides what the user is trying to do.

Decision-making, not fixed rules: the primary path asks the configured LLM to
classify the message via function calling (`classify_intent`) — it can return
several competing hypotheses with a confidence score each, exactly like a
human triaging an inbox would keep more than one possibility in mind for an
ambiguous message. Only when the model can't be reached or degrades to a stub
(no API key configured, same as every other LLMProvider in this codebase)
does a lightweight keyword heuristic step in — a fallback, never the primary
decision path, mirroring how `providers/llm/*` already degrade to STUB_REPLY.
"""
from enum import Enum

from pydantic import BaseModel

from providers.llm.base import ChatMessage, LLMProvider, ToolSpec
from providers.llm.factory import get_llm_provider


class Intent(str, Enum):
    GREETING = "greeting"
    QUESTION = "question"
    REQUEST = "request"
    RESEARCH = "research"
    SCHEDULE = "schedule"
    APPOINTMENT = "appointment"
    STORE = "store"
    CHURCH = "church"
    DOCUMENT = "document"
    TASK = "task"
    REMINDER = "reminder"
    WEB_SEARCH = "web_search"
    FILE = "file"
    IMAGE = "image"
    ADMIN_COMMAND = "admin_command"
    SMALL_TALK = "small_talk"


_INTENT_VALUES = [intent.value for intent in Intent]


class IntentHypothesis(BaseModel):
    intent: Intent
    confidence: float


class IntentResult(BaseModel):
    top: Intent
    hypotheses: list[IntentHypothesis]


_CLASSIFY_INTENT_TOOL = ToolSpec(
    name="classify_intent",
    description=(
        "Registra as hipóteses de intenção identificadas na mensagem do usuário. "
        "Se houver ambiguidade, registre mais de uma hipótese com confiança menor "
        "em vez de forçar uma única categoria."
    ),
    parameters={
        "type": "object",
        "properties": {
            "hypotheses": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string", "enum": _INTENT_VALUES},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["intent", "confidence"],
                },
            }
        },
        "required": ["hypotheses"],
    },
)

_INTENT_SYSTEM_PROMPT = (
    "Você é o mecanismo de análise de intenção do Dario OS. Leia a mensagem do "
    "usuário e chame a ferramenta classify_intent com uma ou mais hipóteses de "
    "intenção (categorias válidas: " + ", ".join(_INTENT_VALUES) + "), cada uma "
    "com uma pontuação de confiança entre 0 e 1. Não responda em texto livre, "
    "apenas chame a ferramenta."
)

# Degrade path only (see module docstring) — not the primary decision mechanism.
_FALLBACK_KEYWORDS: dict[Intent, tuple[str, ...]] = {
    Intent.GREETING: ("oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "e aí", "eae"),
    Intent.SCHEDULE: ("agenda", "agendar", "marcar", "reunião", "reuniao"),
    Intent.APPOINTMENT: ("compromisso", "consulta", "horário", "horario"),
    Intent.REMINDER: ("lembrete", "lembrar", "não esquecer", "nao esquecer"),
    Intent.TASK: ("tarefa", "afazer", "pendência", "pendencia", "to-do", "todo"),
    Intent.STORE: ("loja", "produto", "pedido", "comprar", "cliente", "orçamento", "orcamento"),
    Intent.CHURCH: ("igreja", "culto", "oração", "oracao", "membro", "escala", "pastor"),
    Intent.WEB_SEARCH: ("pesquise na internet", "busque na web", "google", "pesquisar na web"),
    Intent.RESEARCH: ("pesquisa", "pesquisar", "descubra", "informações sobre", "informacoes sobre"),
    Intent.DOCUMENT: ("documento", "pdf", "contrato", "relatório", "relatorio"),
    Intent.FILE: ("arquivo", "anexo"),
    Intent.IMAGE: ("imagem", "foto", "figura"),
    Intent.ADMIN_COMMAND: ("desativar", "ativar", "configurar", "reiniciar", "/admin"),
    Intent.QUESTION: ("?", "como", "quando", "onde", "por que", "porque", "qual"),
}


class IntentEngine:
    """Independent, single-purpose component: message in, intent hypotheses out."""

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self._llm = llm

    def _llm_provider(self) -> LLMProvider:
        return self._llm or get_llm_provider()

    async def classify(self, message: str) -> IntentResult:
        try:
            result = await self._llm_provider().chat(
                [
                    ChatMessage(role="system", content=_INTENT_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=message),
                ],
                tools=[_CLASSIFY_INTENT_TOOL],
            )
        except Exception:  # noqa: BLE001 - classification is best-effort, never blocks the pipeline
            return self._fallback(message)
        call = next((c for c in result.tool_calls if c.name == "classify_intent"), None)
        if call is None:
            return self._fallback(message)

        hypotheses = []
        for raw in call.arguments.get("hypotheses", []):
            if raw.get("intent") not in _INTENT_VALUES:
                continue
            try:
                confidence = float(raw.get("confidence", 0))
            except (TypeError, ValueError):
                continue
            hypotheses.append(IntentHypothesis(intent=Intent(raw["intent"]), confidence=confidence))
        if not hypotheses:
            return self._fallback(message)

        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        return IntentResult(top=hypotheses[0].intent, hypotheses=hypotheses)

    def _fallback(self, message: str) -> IntentResult:
        lowered = message.lower()
        scores: dict[Intent, float] = {}
        for intent, keywords in _FALLBACK_KEYWORDS.items():
            matches = sum(1 for keyword in keywords if keyword in lowered)
            if matches:
                scores[intent] = min(0.9, 0.5 + 0.15 * matches)

        if not scores:
            # No signal at all: keep it honest — two plausible, low-confidence
            # hypotheses rather than a single overconfident guess.
            return IntentResult(
                top=Intent.SMALL_TALK,
                hypotheses=[
                    IntentHypothesis(intent=Intent.SMALL_TALK, confidence=0.4),
                    IntentHypothesis(intent=Intent.QUESTION, confidence=0.3),
                ],
            )

        hypotheses = [
            IntentHypothesis(intent=intent, confidence=confidence)
            for intent, confidence in sorted(scores.items(), key=lambda item: item[1], reverse=True)
        ]
        return IntentResult(top=hypotheses[0].intent, hypotheses=hypotheses)
