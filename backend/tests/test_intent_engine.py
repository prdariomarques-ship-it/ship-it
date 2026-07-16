"""Intent Engine: LLM-driven decision-making as the primary path, a keyword
heuristic only as the degrade path (mirrors how LLMProvider itself degrades
to STUB_REPLY without an API key)."""

import pytest

from orchestrator.intent import Intent, IntentEngine, IntentHypothesis, IntentResult
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
            tool_calls=[
                ToolCallRequest(
                    id="c1", name="classify_intent", arguments={"hypotheses": []}
                )
            ]
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
                    arguments={
                        "hypotheses": [
                            {"intent": "not_a_real_intent", "confidence": 0.9}
                        ]
                    },
                )
            ]
        )
    )
    result = await IntentEngine(llm=llm).classify("oi")
    # Falls back to the heuristic since no valid hypothesis survived.
    assert result.top == Intent.GREETING


# --- Ambiguity detection -------------------------------------------------------
def test_single_high_confidence_hypothesis_is_not_ambiguous():
    result = IntentResult(
        top=Intent.GREETING,
        hypotheses=[IntentHypothesis(intent=Intent.GREETING, confidence=0.95)],
    )
    assert result.is_ambiguous is False


def test_single_low_confidence_hypothesis_is_ambiguous():
    """Even with nothing to compare against, low confidence alone isn't a
    safe enough read of the message."""
    result = IntentResult(
        top=Intent.SMALL_TALK,
        hypotheses=[IntentHypothesis(intent=Intent.SMALL_TALK, confidence=0.4)],
    )
    assert result.is_ambiguous is True


def test_close_competing_hypotheses_are_ambiguous():
    result = IntentResult(
        top=Intent.QUESTION,
        hypotheses=[
            IntentHypothesis(intent=Intent.QUESTION, confidence=0.6),
            IntentHypothesis(intent=Intent.RESEARCH, confidence=0.55),
        ],
    )
    assert result.is_ambiguous is True


def test_clear_leader_over_a_runner_up_is_not_ambiguous():
    result = IntentResult(
        top=Intent.GREETING,
        hypotheses=[
            IntentHypothesis(intent=Intent.GREETING, confidence=0.9),
            IntentHypothesis(intent=Intent.SMALL_TALK, confidence=0.2),
        ],
    )
    assert result.is_ambiguous is False


def test_no_hypotheses_at_all_is_ambiguous():
    result = IntentResult(top=Intent.SMALL_TALK, hypotheses=[])
    assert result.is_ambiguous is True


def test_is_ambiguous_round_trips_through_model_dump():
    """Exposed as a computed field so it survives into the structured log
    payload (CognitivePipeline._log_run dumps intent.hypotheses today; a
    future caller dumping the whole IntentResult gets is_ambiguous for free)."""
    result = IntentResult(
        top=Intent.GREETING,
        hypotheses=[IntentHypothesis(intent=Intent.GREETING, confidence=0.95)],
    )
    assert result.model_dump()["is_ambiguous"] is False
