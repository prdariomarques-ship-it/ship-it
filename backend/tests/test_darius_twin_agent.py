"""DariusTwinAgent: verifies the risk-gate short-circuit -- the one thing
that makes this agent different from a plain BaseAgent subclass. The
underlying run loop (memory injection, planner, executor) is already
covered generically by test_agent_executor.py / test_agents.py."""

from unittest.mock import AsyncMock, patch

import pytest

from agents.darius_twin_agent import DariusTwinAgent
from agents.registry import get_agent
from orchestrator.twin_risk_gate import ESCALATION_MESSAGE, RiskAssessment, RiskCategory


def test_twin_is_registered_and_reachable_by_name():
    assert get_agent("twin").name == "twin"


def test_twin_system_prompt_loads_the_manual():
    prompt = DariusTwinAgent().system_prompt
    assert "DARIUS TWIN" in prompt
    assert len(prompt) > 1000


@pytest.mark.asyncio
async def test_escalation_short_circuits_before_the_executor(monkeypatch):
    agent = DariusTwinAgent()
    escalated = RiskAssessment(
        should_escalate=True,
        category=RiskCategory.LEGAL_MATTER,
        reason="teste",
    )
    with patch(
        "agents.darius_twin_agent.twin_risk_gate.assess",
        new=AsyncMock(return_value=escalated),
    ):
        with patch("agents.base.BaseAgent.run", new=AsyncMock()) as base_run:
            result = await agent.run(db=None, user=None, message="oi")

    assert result.reply == ESCALATION_MESSAGE
    assert result.steps == []
    base_run.assert_not_called()


@pytest.mark.asyncio
async def test_non_escalated_message_falls_through_to_base_run():
    agent = DariusTwinAgent()
    clear = RiskAssessment(should_escalate=False)
    sentinel_result = object()
    with patch(
        "agents.darius_twin_agent.twin_risk_gate.assess",
        new=AsyncMock(return_value=clear),
    ):
        with patch(
            "agents.base.BaseAgent.run", new=AsyncMock(return_value=sentinel_result)
        ) as base_run:
            result = await agent.run(db=None, user=None, message="bom dia")

    assert result is sentinel_result
    base_run.assert_awaited_once()
