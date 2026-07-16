"""Priority Engine: LLM decision as the primary path, keyword heuristic as
the degrade path, plus the non-LLM `quick_priority_hint` used at webhook time."""

import pytest

from orchestrator.intent import Intent, IntentHypothesis, IntentResult
from orchestrator.priority import Priority, PriorityEngine, quick_priority_hint
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


def _intent(top: Intent) -> IntentResult:
    return IntentResult(
        top=top, hypotheses=[IntentHypothesis(intent=top, confidence=0.9)]
    )


@pytest.mark.asyncio
async def test_llm_decision_sets_level_and_reason():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="classify_priority",
                    arguments={"level": "urgent", "reason": "socorro"},
                )
            ]
        )
    )
    result = await PriorityEngine(llm=llm).classify(
        "preciso de ajuda urgente", _intent(Intent.REQUEST)
    )
    assert result.level == Priority.URGENT
    assert result.reason == "socorro"


@pytest.mark.asyncio
async def test_degrades_to_heuristic_without_tool_call():
    llm = ScriptedLLM(LLMResult(content="stub"))
    result = await PriorityEngine(llm=llm).classify(
        "oi tudo bem?", _intent(Intent.GREETING)
    )
    assert result.level == Priority.LOW


@pytest.mark.asyncio
async def test_heuristic_detects_urgent_keyword():
    llm = ScriptedLLM(LLMResult(content="stub"))
    result = await PriorityEngine(llm=llm).classify(
        "é urgente, preciso agora", _intent(Intent.REQUEST)
    )
    assert result.level == Priority.URGENT


@pytest.mark.asyncio
async def test_heuristic_treats_admin_command_as_high():
    llm = ScriptedLLM(LLMResult(content="stub"))
    result = await PriorityEngine(llm=llm).classify(
        "desativar o robô", _intent(Intent.ADMIN_COMMAND)
    )
    assert result.level == Priority.HIGH


@pytest.mark.asyncio
async def test_invalid_level_from_model_falls_back():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="classify_priority",
                    arguments={"level": "catastrophic"},
                )
            ]
        )
    )
    result = await PriorityEngine(llm=llm).classify("oi", _intent(Intent.GREETING))
    assert result.level == Priority.LOW  # heuristic fallback for a greeting


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
async def test_degrades_to_heuristic_when_the_provider_raises():
    result = await PriorityEngine(llm=RaisingLLM()).classify(
        "é urgente, socorro", _intent(Intent.REQUEST)
    )
    assert result.level == Priority.URGENT


def test_quick_priority_hint_never_calls_a_model():
    assert quick_priority_hint("isso é urgente, socorro") == Priority.URGENT
    assert quick_priority_hint("preciso disso hoje") == Priority.HIGH
    assert quick_priority_hint("oi, tudo bem?") == Priority.NORMAL
