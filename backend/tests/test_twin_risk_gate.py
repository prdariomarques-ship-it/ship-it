"""Twin Risk Gate: LLM decision as the primary path, keyword heuristic as
the degrade path -- same contract as PriorityEngine (test_priority_engine.py),
applied to the escalation rules in agents/prompts/darius_twin_manual.md
(section 93, "QUANDO PRECISA ESCALAR PARA DÁRIO")."""

import pytest

from orchestrator.twin_risk_gate import (
    ESCALATION_MESSAGE,
    RiskCategory,
    TwinRiskGate,
    quick_risk_hint,
)
from providers.llm.base import LLMProvider, LLMResult, ToolCallRequest


class ScriptedLLM(LLMProvider):
    name = "scripted"

    def __init__(self, result: LLMResult) -> None:
        self._result = result

    @property
    def enabled(self) -> bool:
        return True

    async def chat(self, messages, tools=None) -> LLMResult:
        return self._result

    async def embed(self, text: str) -> list[float]:
        return [0.0]


class RaisingLLM(LLMProvider):
    name = "raising"

    @property
    def enabled(self) -> bool:
        return True

    async def chat(self, messages, tools=None) -> LLMResult:
        raise RuntimeError("provider unreachable")

    async def embed(self, text: str) -> list[float]:
        return [0.0]


@pytest.mark.asyncio
async def test_llm_escalation_sets_category_and_reason():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="assess_risk",
                    arguments={
                        "should_escalate": True,
                        "category": "legal_matter",
                        "reason": "cliente mencionou processo",
                    },
                )
            ]
        )
    )
    result = await TwinRiskGate(llm=llm).assess("recebi uma notificação do meu advogado")
    assert result.should_escalate is True
    assert result.category == RiskCategory.LEGAL_MATTER
    assert result.reason == "cliente mencionou processo"


@pytest.mark.asyncio
async def test_llm_no_escalation_for_ordinary_message():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="assess_risk",
                    arguments={"should_escalate": False},
                )
            ]
        )
    )
    result = await TwinRiskGate(llm=llm).assess("bom dia, tudo bem?")
    assert result.should_escalate is False
    assert result.category == RiskCategory.NONE


@pytest.mark.asyncio
async def test_escalation_without_category_defaults_to_out_of_scope():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1", name="assess_risk", arguments={"should_escalate": True}
                )
            ]
        )
    )
    result = await TwinRiskGate(llm=llm).assess("pedido fora do escopo")
    assert result.should_escalate is True
    assert result.category == RiskCategory.OUT_OF_SCOPE


@pytest.mark.asyncio
async def test_degrades_to_heuristic_without_tool_call():
    llm = ScriptedLLM(LLMResult(content="stub, sem tool call"))
    result = await TwinRiskGate(llm=llm).assess(
        "quero resgatar tudo agora, me confirma a operação"
    )
    assert result.should_escalate is True
    assert result.category == RiskCategory.FINANCIAL_OPERATION


@pytest.mark.asyncio
async def test_degrades_to_heuristic_when_provider_raises():
    result = await TwinRiskGate(llm=RaisingLLM()).assess("é você mesmo respondendo?")
    assert result.should_escalate is True
    assert result.category == RiskCategory.IDENTITY_DOUBT


@pytest.mark.asyncio
async def test_heuristic_fallback_allows_ordinary_message_through():
    llm = ScriptedLLM(LLMResult(content="stub"))
    result = await TwinRiskGate(llm=llm).assess("bom dia! como você está?")
    assert result.should_escalate is False


def test_quick_risk_hint_never_calls_a_model():
    assert quick_risk_hint("quero sacar meu dinheiro agora").should_escalate
    assert quick_risk_hint("vou processar vocês na justiça").should_escalate
    assert quick_risk_hint("qual minha senha do app?").should_escalate
    assert not quick_risk_hint("oi, bom dia, tudo bem?").should_escalate


def test_escalation_message_matches_manual_section_93():
    # Verbatim line from agents/prompts/darius_twin_manual.md, section 93 --
    # the one phrasing designed to escalate without breaking the
    # never-reveal-automation identity rule. A change here should only ever
    # follow a change to the manual itself.
    assert ESCALATION_MESSAGE == (
        "Esse ponto eu prefiro confirmar pessoalmente com você antes de te responder."
    )
