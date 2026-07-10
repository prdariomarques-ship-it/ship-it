"""Intent Engine: LLM-driven decision-making as the primary path, a keyword
heuristic only as the degrade path (mirrors how LLMProvider itself degrades
to STUB_REPLY without an API key)."""
import pytest

from orchestrator.intent import Intent, IntentEngine
from providers.llm.base import ChatMessage, LLMProvider, LLMResult, ToolCallRequest


class ScriptedLLM(LLMProvider):
    name = "scripted"

    def __init__(self, result: LLMResult) -> None:
        self._result = result
        self.received: list[list[ChatMessage]] = []

    @property
    def enabled(self) -> bool:
        return True

    async def chat(self, messages, tools=None) -> LLMResult:
        self.received.append(list(messages))
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
async def test_llm_decision_returns_top_hypothesis_by_confidence():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="classify_intent",
                    arguments={
                        "hypotheses": [
                            {"intent": "question", "confidence": 0.4},
                            {"intent": "store", "confidence": 0.8},
                        ]
                    },
                )
            ]
        )
    )
    result = await IntentEngine(llm=llm).classify("quanto custa o produto X?")
    assert result.top == Intent.STORE
    assert result.hypotheses[0].intent == Intent.STORE
    assert len(result.hypotheses) == 2


@pytest.mark.asyncio
async def test_llm_can_return_multiple_hypotheses_for_ambiguous_message():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="classify_intent",
                    arguments={
                        "hypotheses": [
                            {"intent": "task", "confidence": 0.35},
                            {"intent": "reminder", "confidence": 0.33},
                            {"intent": "schedule", "confidence": 0.3},
                        ]
                    },
                )
            ]
        )
    )
    result = await IntentEngine(llm=llm).classify("marca isso pra mim depois")
    assert len(result.hypotheses) == 3


@pytest.mark.asyncio
async def test_degrades_to_heuristic_when_model_gives_no_tool_call():
    llm = ScriptedLLM(LLMResult(content="apenas texto, sem function calling"))
    result = await IntentEngine(llm=llm).classify("Bom dia, tudo bem?")
    assert result.top == Intent.GREETING
    assert len(result.hypotheses) >= 1


@pytest.mark.asyncio
async def test_degrades_to_heuristic_when_arguments_are_garbage():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[ToolCallRequest(id="c1", name="classify_intent", arguments={"hypotheses": []})]
        )
    )
    result = await IntentEngine(llm=llm).classify("olá")
    assert result.top == Intent.GREETING


@pytest.mark.asyncio
async def test_heuristic_fallback_returns_multiple_hypotheses_when_nothing_matches():
    llm = ScriptedLLM(LLMResult(content="stub"))
    result = await IntentEngine(llm=llm).classify("xyzabc 12345 blah")
    assert len(result.hypotheses) >= 2
    assert all(0 <= h.confidence <= 1 for h in result.hypotheses)


@pytest.mark.asyncio
async def test_heuristic_fallback_detects_store_keywords():
    llm = ScriptedLLM(LLMResult(content="stub"))
    result = await IntentEngine(llm=llm).classify("quero fazer um pedido na loja")
    assert result.top == Intent.STORE


@pytest.mark.asyncio
async def test_degrades_to_heuristic_when_the_provider_raises():
    """A raised exception (provider down/network error) — not just a missing
    tool call — must never crash the pipeline at the classification stage."""
    result = await IntentEngine(llm=RaisingLLM()).classify("bom dia")
    assert result.top == Intent.GREETING


@pytest.mark.asyncio
async def test_unknown_intent_labels_from_model_are_discarded():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="classify_intent",
                    arguments={"hypotheses": [{"intent": "not_a_real_intent", "confidence": 0.9}]},
                )
            ]
        )
    )
    result = await IntentEngine(llm=llm).classify("oi")
    # Falls back to the heuristic since no valid hypothesis survived.
    assert result.top == Intent.GREETING
