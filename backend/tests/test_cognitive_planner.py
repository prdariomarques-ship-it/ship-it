"""Cognitive Planner: decides step decomposition + agent routing, never calls
a tool itself — a Plan is data, something else executes it."""

import pytest

from agents.registry import list_agents
from orchestrator.intent import Intent, IntentHypothesis, IntentResult
from orchestrator.planning import CognitivePlanner, _MAX_PLAN_STEPS
from orchestrator.priority import Priority, PriorityResult
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


_PRIORITY = PriorityResult(level=Priority.NORMAL, reason="")


@pytest.mark.asyncio
async def test_fallback_plan_is_single_step_with_the_original_message():
    llm = ScriptedLLM(LLMResult(content="stub, sem tool call"))
    plan = await CognitivePlanner(llm=llm).create_plan(
        "Bom dia, preciso de ajuda", _intent(Intent.GREETING), _PRIORITY
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].objective == "Bom dia, preciso de ajuda"
    assert plan.steps[0].agent == "assistant"
    assert plan.needs_confirmation is False


@pytest.mark.asyncio
async def test_fallback_plan_uses_intent_hint_when_available():
    llm = ScriptedLLM(LLMResult(content="stub"))
    plan = await CognitivePlanner(llm=llm).create_plan(
        "marca uma tarefa", _intent(Intent.TASK), _PRIORITY
    )
    assert plan.steps[0].agent == "personal"


@pytest.mark.asyncio
async def test_llm_decision_produces_a_multi_step_plan():
    agent_names = [a.name for a in list_agents()]
    assert "personal" in agent_names and "church" in agent_names

    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="create_plan",
                    arguments={
                        "steps": [
                            {
                                "objective": "Marcar reunião amanhã às 14h",
                                "agent": "personal",
                                "depends_on": [],
                            },
                            {
                                "objective": "Enviar mensagem para o grupo da igreja",
                                "agent": "church",
                                "depends_on": [0],
                            },
                        ],
                        "needs_confirmation": False,
                    },
                )
            ]
        )
    )
    plan = await CognitivePlanner(llm=llm).create_plan(
        "Marque uma reunião amanhã às 14h e depois envie uma mensagem para o grupo da igreja.",
        _intent(Intent.SCHEDULE),
        _PRIORITY,
    )
    assert len(plan.steps) == 2
    assert plan.steps[0].agent == "personal"
    assert plan.steps[1].agent == "church"
    assert plan.steps[1].depends_on == [0]


@pytest.mark.asyncio
async def test_unknown_agent_name_from_model_is_replaced_by_intent_hint():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="create_plan",
                    arguments={
                        "steps": [{"objective": "comprar item", "agent": "nao-existe"}]
                    },
                )
            ]
        )
    )
    plan = await CognitivePlanner(llm=llm).create_plan(
        "comprar produto", _intent(Intent.STORE), _PRIORITY
    )
    assert plan.steps[0].agent == "store"


@pytest.mark.asyncio
async def test_plan_is_capped_at_max_steps():
    steps = [
        {"objective": f"passo {i}", "agent": "assistant"}
        for i in range(_MAX_PLAN_STEPS + 3)
    ]
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(id="c1", name="create_plan", arguments={"steps": steps})
            ]
        )
    )
    plan = await CognitivePlanner(llm=llm).create_plan(
        "várias coisas", _intent(Intent.REQUEST), _PRIORITY
    )
    assert len(plan.steps) == _MAX_PLAN_STEPS


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
async def test_degrades_to_fallback_plan_when_the_provider_raises():
    plan = await CognitivePlanner(llm=RaisingLLM()).create_plan(
        "oi", _intent(Intent.GREETING), _PRIORITY
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].agent == "assistant"


@pytest.mark.asyncio
async def test_needs_confirmation_flag_is_propagated():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="create_plan",
                    arguments={
                        "steps": [
                            {"objective": "cancelar todos os pedidos", "agent": "store"}
                        ],
                        "needs_confirmation": True,
                    },
                )
            ]
        )
    )
    plan = await CognitivePlanner(llm=llm).create_plan(
        "cancela tudo", _intent(Intent.STORE), _PRIORITY
    )
    assert plan.needs_confirmation is True


# --- Plan confidence ---------------------------------------------------------
@pytest.mark.asyncio
async def test_confidence_from_the_model_is_propagated():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="create_plan",
                    arguments={
                        "steps": [{"objective": "marcar reunião", "agent": "personal"}],
                        "confidence": 0.82,
                    },
                )
            ]
        )
    )
    plan = await CognitivePlanner(llm=llm).create_plan(
        "marca uma reunião", _intent(Intent.SCHEDULE), _PRIORITY
    )
    assert plan.confidence == 0.82


@pytest.mark.asyncio
async def test_confidence_defaults_to_1_when_the_model_omits_it():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="create_plan",
                    arguments={"steps": [{"objective": "x", "agent": "assistant"}]},
                )
            ]
        )
    )
    plan = await CognitivePlanner(llm=llm).create_plan(
        "x", _intent(Intent.QUESTION), _PRIORITY
    )
    assert plan.confidence == 1.0


@pytest.mark.asyncio
async def test_confidence_is_clamped_to_the_0_1_range():
    llm = ScriptedLLM(
        LLMResult(
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="create_plan",
                    arguments={
                        "steps": [{"objective": "x", "agent": "assistant"}],
                        "confidence": 5.0,
                    },
                )
            ]
        )
    )
    plan = await CognitivePlanner(llm=llm).create_plan(
        "x", _intent(Intent.QUESTION), _PRIORITY
    )
    assert plan.confidence == 1.0


@pytest.mark.asyncio
async def test_fallback_plan_has_low_confidence():
    """A keyword-hint single-step plan is a degraded guess, never a reasoned
    decision -- its confidence must reflect that, not claim certainty."""
    plan = await CognitivePlanner(llm=RaisingLLM()).create_plan(
        "oi", _intent(Intent.GREETING), _PRIORITY
    )
    assert plan.confidence == 0.3
