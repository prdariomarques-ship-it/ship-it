"""Twin Risk Gate: safety escalation gate for the Darius Twin impersonation
agent (`agents.darius_twin_agent`).

The Twin replies on Dário's personal WhatsApp number in first person, as if
it were Dário himself (see `agents/prompts/darius_twin_manual.md`,
"Instrução de identidade") -- a materially higher-risk failure mode than
every disclosed-assistant agent in this registry. A wrong or overconfident
reply from `personal`/`assistant`/`store` is a bad answer from a labeled
bot; the same failure from the Twin is words put in a real person's mouth,
sent to real contacts -- including his own wealth-management clients
(compliance-sensitive) and church congregation (pastoral-care-sensitive).

The manual itself specifies exactly when it must stop answering
autonomously and hand off instead (section 93, "QUANDO PRECISA ESCALAR
PARA DÁRIO"): a relevant financial decision without enough context, a
financial operation, a serious complaint, a legal matter, a personal
conflict, confidential information, a request requiring authorization,
doubt about who's actually replying, risk of causing harm, or anything
outside the Twin's scope. This module turns that list into an enforced
check that runs *before* the Twin's reply is allowed out, instead of
trusting the model to self-police it inside one giant system prompt.

Same shape as `orchestrator.priority.PriorityEngine` on purpose: LLM
function-calling classification as the primary path, a keyword heuristic
as the degrade path when the LLM call itself fails -- that pattern is
already proven in this codebase for "classify this inbound message into a
small fixed enum, cheaply, every time," which is exactly this job.
"""

from enum import Enum

from pydantic import BaseModel

from providers.llm.base import ChatMessage, LLMProvider, ToolSpec
from providers.llm.factory import get_llm_provider

# Verbatim from the manual, section 93 -- this is the one line specifically
# written to escalate without breaking the "never reveal this is
# automated" identity rule ("Instrução de identidade"). Never rephrase it
# ad hoc elsewhere; change it here if it ever needs to change.
ESCALATION_MESSAGE = (
    "Esse ponto eu prefiro confirmar pessoalmente com você antes de te responder."
)


class RiskCategory(str, Enum):
    FINANCIAL_DECISION = "financial_decision"
    FINANCIAL_OPERATION = "financial_operation"
    SERIOUS_COMPLAINT = "serious_complaint"
    LEGAL_MATTER = "legal_matter"
    PERSONAL_CONFLICT = "personal_conflict"
    CONFIDENTIAL_INFORMATION = "confidential_information"
    AUTHORIZATION_REQUEST = "authorization_request"
    IDENTITY_DOUBT = "identity_doubt"
    HARM_RISK = "harm_risk"
    OUT_OF_SCOPE = "out_of_scope"
    NONE = "none"


class RiskAssessment(BaseModel):
    should_escalate: bool
    category: RiskCategory = RiskCategory.NONE
    reason: str = ""


_RISK_VALUES = [category.value for category in RiskCategory]

_RISK_TOOL = ToolSpec(
    name="assess_risk",
    description=(
        "Classifica se esta mensagem exige que o Twin do Dário pare de "
        "responder autonomamente e escale para o Dário real antes de responder."
    ),
    parameters={
        "type": "object",
        "properties": {
            "should_escalate": {"type": "boolean"},
            "category": {"type": "string", "enum": _RISK_VALUES},
            "reason": {"type": "string"},
        },
        "required": ["should_escalate"],
    },
)

_RISK_SYSTEM_PROMPT = (
    "Você é o gate de segurança do Twin digital do Dário no WhatsApp pessoal dele. "
    "O Twin responde em primeira pessoa como se fosse o próprio Dário, para clientes "
    "de investimento e membros da igreja dele -- por isso deve parar de responder "
    "sozinho e escalar (should_escalate=true) sempre que a mensagem do contato "
    "envolver: decisão financeira relevante sem contexto suficiente, operação "
    "financeira (movimentar, resgatar, aplicar, transferir, sacar), reclamação "
    "grave, assunto jurídico, conflito pessoal, informação confidencial, "
    "solicitação que exija autorização, dúvida sobre a identidade de quem está "
    "respondendo, risco de causar prejuízo a alguém, ou pedido fora do escopo de "
    "um assistente pessoal (pastoral, investimentos, filosofia aplicada, conversa "
    "cotidiana). Chame assess_risk com should_escalate, a categoria mais próxima e "
    "uma justificativa curta. Na dúvida, escale -- o custo de escalar sem "
    "necessidade é uma resposta adiada; o custo de não escalar é uma resposta "
    "indevida em nome do Dário real."
)

# Keyword fallback -- used only when the LLM call itself fails (network,
# provider outage, timeout), same "classification must never block the
# pipeline" contract as PriorityEngine/IntentEngine. Deliberately biased
# toward over-escalating: a false positive costs one deferred reply --
# visible, not silent, and the manual's own section-93 wording reads
# naturally either way. A false negative costs an unauthorized word in
# Dário's mouth to a real client or congregant. Not a symmetric trade.
_ESCALATION_KEYWORDS: dict[RiskCategory, tuple[str, ...]] = {
    RiskCategory.FINANCIAL_OPERATION: (
        "resgatar",
        "resgate",
        "aplicar",
        "aplicação",
        "aplicacao",
        "transferir",
        "transferência",
        "transferencia",
        "sacar",
        "saque",
        "movimentar",
        "investir agora",
        "comprar agora",
        "vender agora",
        "confirma a operação",
        "confirma a operacao",
    ),
    RiskCategory.LEGAL_MATTER: (
        "processo",
        "processar",
        "advogado",
        "jurídico",
        "juridico",
        "contrato",
        "notificação extrajudicial",
        "notificacao extrajudicial",
        "boletim de ocorrência",
        "boletim de ocorrencia",
    ),
    RiskCategory.SERIOUS_COMPLAINT: (
        "reclamação",
        "reclamacao",
        "reclamar",
        "insatisfeito",
        "prejuízo",
        "prejuizo",
        "perdi dinheiro",
        "vou cancelar",
        "quero meu dinheiro de volta",
    ),
    RiskCategory.CONFIDENTIAL_INFORMATION: (
        "senha",
        "cpf",
        "número da conta",
        "numero da conta",
        "saldo",
        "extrato",
        "cartão",
        "cartao",
    ),
    RiskCategory.AUTHORIZATION_REQUEST: (
        "autoriza",
        "autorização",
        "autorizacao",
        "pode confirmar",
        "assinar",
        "procuração",
        "procuracao",
    ),
    RiskCategory.IDENTITY_DOUBT: (
        "é você mesmo",
        "e voce mesmo",
        "é vc mesmo",
        "e vc mesmo",
        "é um robô",
        "e um robo",
        "é bot",
        "e bot",
        "é ia",
        "e ia",
        "isso é automático",
        "isso e automatico",
    ),
    RiskCategory.HARM_RISK: (
        "vou me matar",
        "quero morrer",
        "não aguento mais",
        "nao aguento mais",
        "socorro",
    ),
}


def quick_risk_hint(message: str) -> RiskAssessment:
    """Fast, non-LLM keyword scan -- same role as
    `orchestrator.priority.quick_priority_hint`: never blocks, doubles as
    `TwinRiskGate`'s own degrade path and is safe to call standalone."""
    lowered = message.lower()
    for category, keywords in _ESCALATION_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return RiskAssessment(
                should_escalate=True,
                category=category,
                reason=f"palavra-chave de risco detectada ({category.value})",
            )
    return RiskAssessment(should_escalate=False)


class TwinRiskGate:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self._llm = llm

    def _llm_provider(self) -> LLMProvider:
        return self._llm or get_llm_provider()

    async def assess(self, message: str) -> RiskAssessment:
        try:
            result = await self._llm_provider().chat(
                [
                    ChatMessage(role="system", content=_RISK_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=message),
                ],
                tools=[_RISK_TOOL],
            )
        except Exception:  # noqa: BLE001 - classification is best-effort, never blocks the pipeline
            return quick_risk_hint(message)

        call = next((c for c in result.tool_calls if c.name == "assess_risk"), None)
        if call is None:
            return quick_risk_hint(message)

        should_escalate = bool(call.arguments.get("should_escalate", False))
        category_raw = call.arguments.get("category")
        category = (
            RiskCategory(category_raw)
            if category_raw in _RISK_VALUES
            else RiskCategory.NONE
        )
        if should_escalate and category is RiskCategory.NONE:
            category = RiskCategory.OUT_OF_SCOPE
        return RiskAssessment(
            should_escalate=should_escalate,
            category=category,
            reason=str(call.arguments.get("reason", "")),
        )


twin_risk_gate = TwinRiskGate()
