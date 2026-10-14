# ruff: noqa: F811
"""Exemplos de estilo chegam aos agentes da Loja, do B2B e da Azusa, cada um SO com a propria instancia (handler real de entrada).

Substituidos: o orquestrador (captura os argumentos) e a busca vetorial. Prova a fiacao e o isolamento por instancia; a qualidade da
recuperacao com embeddings reais nao e provada aqui."""
from unittest.mock import AsyncMock

import pytest

from agents.executor import AgentResult
from tests.test_message_age_guard import _jobs, _msg, _run, flow  # noqa: F401
from tests.test_store_followups import STORE, env  # noqa: F401

EXAMPLE = "Pergunta: Tem a branca?\nResposta: Tem sim, vem buscar."
FLOWS = [(STORE, "5511999993001", "store"), ("b2b-sales", "5511999993002", "b2b"), ("azusa-church", "5511999993003", "azusa_intake")]


@pytest.fixture
def captured(flow, monkeypatch):
    calls, searches = [], AsyncMock(return_value=[EXAMPLE])

    async def fake_run(**kwargs):
        calls.append(kwargs)
        return AgentResult(reply="Tem sim.")

    monkeypatch.setattr("orchestrator.service.ai_orchestrator.run", fake_run)
    monkeypatch.setattr("services.style_distill.retrieve_style_examples", searches)
    monkeypatch.setattr(flow.s, "style_examples_enabled", True)
    flow.calls, flow.searches = calls, searches
    return flow


@pytest.mark.parametrize("instance, phone, agent", FLOWS)
async def test_agente_recebe_os_exemplos_da_propria_instancia(captured, monkeypatch, instance, phone, agent):
    monkeypatch.setattr(captured.s, "style_instances", f"{STORE},b2b-sales,azusa-church")
    cid, mid = await _msg(captured, "Tem tinta branca?", age_seconds=10, instance=instance, phone=phone)
    await _run(captured, cid, mid, instance)
    (call,) = captured.calls
    assert call["agent_name"] == agent
    (block,) = call["extra_system"]
    assert EXAMPLE in block and "a equipe desta conta" in block
    captured.searches.assert_awaited_once_with("Tem tinta branca?", instance)  # so a propria instancia e consultada
    assert [j.payload["content"] for j in await _jobs(captured)] == ["Tem sim."]


@pytest.mark.parametrize("instance, phone, agent", FLOWS)
async def test_instancia_fora_da_lista_roda_exatamente_como_antes(captured, monkeypatch, instance, phone, agent):
    monkeypatch.setattr(captured.s, "style_instances", "pessoal-teste")          # nenhuma das tres listadas
    cid, mid = await _msg(captured, "Tem tinta branca?", age_seconds=10, instance=instance, phone=phone)
    await _run(captured, cid, mid, instance)
    (call,) = captured.calls
    assert "extra_system" not in call                                              # a chamada nem muda de assinatura
    captured.searches.assert_not_awaited()


async def test_com_a_chave_de_uso_desligada_nenhum_agente_recebe_nada(captured, monkeypatch):
    monkeypatch.setattr(captured.s, "style_examples_enabled", False)
    monkeypatch.setattr(captured.s, "style_instances", f"{STORE},b2b-sales,azusa-church")
    for instance, phone, _agent in FLOWS:
        cid, mid = await _msg(captured, "Tem tinta branca?", age_seconds=10, instance=instance, phone="5511999994" + phone[-3:])
        await _run(captured, cid, mid, instance)
    assert all("extra_system" not in call for call in captured.calls) and len(captured.calls) == 3
    captured.searches.assert_not_awaited()


async def test_orquestrador_repassa_o_bloco_ao_agente_so_quando_ele_existe(env, monkeypatch):
    from orchestrator.service import ai_orchestrator

    class Owner:
        id = 1

    seen = []

    async def fake_agent_run(self, **kwargs):
        seen.append(kwargs)
        return AgentResult(reply="ok")

    monkeypatch.setattr("agents.base.BaseAgent.run", fake_agent_run)
    async with env.sessions() as db:
        await ai_orchestrator.run(db=db, user=Owner(), message="oi", agent_name="personal", extra_system=["BLOCO"])
        await ai_orchestrator.run(db=db, user=Owner(), message="oi", agent_name="personal")
    assert seen[0]["extra_system"] == ["BLOCO"]
    assert "extra_system" not in seen[1]                     # sem exemplos a chamada e identica a de antes
