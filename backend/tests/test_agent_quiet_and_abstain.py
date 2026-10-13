# ruff: noqa: F811
"""Agentes quietos com atendimento humano, abstenção sem informação confiável e sem reapresentação repetida (Loja/B2B/Azusa/Twin).

Pelo handler real de mensagem recebida; só o LLM/orquestrador é substituído."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import jobs.handlers as handlers
from agents.executor import AgentResult, ExecutedStep
from models.contact import Contact
from models.log import LogEntry
from models.message import Message, MessageDirection, MessageMediaType
from services import conversation_control
from tests.test_message_age_guard import LIMIT, Reached, _jobs, _msg, _run, flow  # noqa: F401
from tests.test_store_followups import STORE, env  # noqa: F401

FLOWS = [(STORE, "5511999991001"), ("b2b-sales", "5511999991002"), ("azusa-church", "5511999991003"), ("pessoal-teste", "5511999991004")]


async def _pause(env, contact_id, instance):
    async with env.sessions() as db:
        await conversation_control.pause(db, contact_id, instance, f"human-{contact_id}-{instance}", "atendimento humano")
        await db.commit()


@pytest.mark.parametrize("instance, phone", FLOWS)
async def test_conversa_em_atendimento_humano_o_agente_nao_age(flow, instance, phone):
    cid, mid = await _msg(flow, "Quero tinta", age_seconds=10, instance=instance, phone=phone)
    await _pause(flow, cid, instance)
    await _run(flow, cid, mid, instance)                                   # o agente (que explodiria com Reached) não é chamado
    assert await _jobs(flow) == []


@pytest.mark.parametrize("instance, phone", FLOWS)
async def test_pausa_de_uma_instancia_nao_silencia_as_outras(flow, instance, phone):
    """Isolamento: o dono conversando na LOJA não pausa o mesmo contato no B2B/Azusa/pessoal, e vice-versa."""
    cid, mid = await _msg(flow, "Quero tinta", age_seconds=10, instance=instance, phone=phone)
    await _pause(flow, cid, "outra-instancia")
    with pytest.raises(Reached):
        await _run(flow, cid, mid, instance)


async def test_parar_continua_sendo_registrado_com_a_conversa_pausada(flow):
    cid, mid = await _msg(flow, "PARAR", age_seconds=10, instance=STORE, phone="5511999991005")
    await _pause(flow, cid, STORE)
    await _run(flow, cid, mid, STORE)
    async with flow.sessions() as db:
        assert (await db.get(Contact, cid)).preferences["store_contact_opt_out"] is True


def _result(reply, *tools):
    return AgentResult(reply=reply, steps=[ExecutedStep(tool=t, arguments={}, result="{}", status="ok") for t in tools])


async def test_sem_informacao_confiavel_o_agente_nao_responde(flow, monkeypatch):
    async def run(*a, **k):
        return _result("Acho que sim, deve ter na loja.", "search_products", "report_unknown")
    monkeypatch.setattr("orchestrator.service.ai_orchestrator.run", run)
    cid, mid = await _msg(flow, "Vocês fazem tinta antichamas hospitalar?", age_seconds=10, instance=STORE, phone="5511999991006")
    await _run(flow, cid, mid, STORE)
    assert await _jobs(flow) == []                                         # nada foi enviado ao cliente


async def test_com_informacao_o_agente_responde_normalmente(flow, monkeypatch):
    async def run(*a, **k):
        return _result("Temos sim, a lata de 18L.", "search_products")
    monkeypatch.setattr("orchestrator.service.ai_orchestrator.run", run)
    cid, mid = await _msg(flow, "Tem tinta branca?", age_seconds=10, instance=STORE, phone="5511999991007")
    await _run(flow, cid, mid, STORE)
    assert [j.payload["content"] for j in await _jobs(flow)] == ["Temos sim, a lata de 18L."]


async def test_ferramenta_registra_a_lacuna_no_log_do_dario_os(flow):
    from agents.tools.base import ToolContext
    from agents.tools.domain import report_unknown_tool
    async with flow.sessions() as db:
        out = json.loads(await report_unknown_tool.handler(ToolContext(db=db, user=None, contact_id=42), question="tinta antichamas hospitalar?", reason="fora do catálogo"))  # type: ignore[arg-type]
    assert out["registered"] is True and "Não envie" in out["instruction"]
    async with flow.sessions() as db:
        (entry,) = (await db.scalars(select(LogEntry).where(LogEntry.source == "store_agent:unknown"))).all()
    assert entry.level == "warning" and entry.payload == {"contact_id": 42, "question": "tinta antichamas hospitalar?", "reason": "fora do catálogo"}


def test_agente_da_loja_tem_a_ferramenta_e_as_regras_no_prompt():
    from agents.store_agent import StoreAgent
    agent = StoreAgent()
    assert "report_unknown" in [t.name for t in agent.tools]
    assert "NÃO responder" in agent.system_prompt and "Não se apresente como assistente" in agent.system_prompt


# ------------------------------------------------------------------------------------------------ reapresentação repetida
INTRO = "Aqui é o assistente virtual da Marquescolor. Temos a tinta, sim."


async def _contact_with_outbound(flow, hours_ago):
    async with flow.sessions() as db:
        c = Contact(name="C", phone="5511999992000", preferences={})
        db.add(c)
        await db.flush()
        if hours_ago is not None:
            db.add(Message(contact_id=c.id, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType.TEXT, content="oi",
                           whatsapp_instance=STORE, created_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago)))
        await db.commit()
        return c.id


@pytest.mark.parametrize("hours_ago, expected", [(1, "Temos a tinta, sim."), (None, INTRO), (30, INTRO)])
async def test_apresentacao_so_some_se_o_bot_ja_falou_na_janela(flow, hours_ago, expected):
    cid = await _contact_with_outbound(flow, hours_ago)
    async with flow.sessions() as db:
        assert await handlers._drop_repeated_intro(db, flow.s, cid, STORE, INTRO) == expected


@pytest.mark.parametrize("reply", [
    "Aqui é o assistente virtual da Marquescolor.",                    # só a apresentação: não deixa a resposta vazia
    "Temos a tinta. Sou o assistente e posso ajudar.",                  # no meio do texto: não mexe
    "Posso ajudar com o orçamento. Aqui é o assistente da loja.",
])
async def test_so_remove_a_frase_inicial_e_nunca_deixa_a_resposta_vazia(flow, reply):
    cid = await _contact_with_outbound(flow, 1)
    async with flow.sessions() as db:
        assert await handlers._drop_repeated_intro(db, flow.s, cid, STORE, reply) == reply


async def test_chave_zero_desliga_o_filtro(flow, monkeypatch):
    monkeypatch.setattr(flow.s, "store_intro_suppress_hours", 0)
    cid = await _contact_with_outbound(flow, 1)
    async with flow.sessions() as db:
        assert await handlers._drop_repeated_intro(db, flow.s, cid, STORE, INTRO) == INTRO


async def test_pelo_handler_a_segunda_resposta_nao_se_reapresenta(flow, monkeypatch):
    async def run(*a, **k):
        return _result(INTRO, "search_products")
    monkeypatch.setattr("orchestrator.service.ai_orchestrator.run", run)
    cid, mid = await _msg(flow, "Tem tinta?", age_seconds=10, instance=STORE, phone="5511999992001")
    await _run(flow, cid, mid, STORE)                                      # 1ª resposta: ainda não houve saída do bot
    async with flow.sessions() as db:
        db.add(Message(contact_id=cid, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType.TEXT, content=INTRO, whatsapp_instance=STORE))
        await db.commit()
    async with flow.sessions() as db:                                       # mesmo contato: 2ª pergunta
        m = Message(contact_id=cid, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content="E a de 3,6L?", whatsapp_instance=STORE)
        db.add(m)
        await db.commit()
        mid_same = m.id
    await _run(flow, cid, mid_same, STORE)
    contents = [j.payload["content"] for j in await _jobs(flow) if j.payload["to"] == "5511999992001"]
    assert contents == [INTRO, "Temos a tinta, sim."]


# ------------------------------------------------------------------------------------------------ revisão: instância, autoria, "quem é você?"
async def _seed_outbound(flow, *, instance=STORE, human=False, hours_ago=1):
    async with flow.sessions() as db:
        c = Contact(name="C", phone="5511999992100", preferences={})
        db.add(c)
        await db.flush()
        db.add(Message(contact_id=c.id, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType.TEXT, content="oi",
                       whatsapp_instance=instance, sent_by_human=human, created_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago)))
        await db.commit()
        return c.id


async def test_mensagem_de_humano_nao_conta_como_o_bot_ja_ter_falado(flow):
    cid = await _seed_outbound(flow, human=True)
    async with flow.sessions() as db:
        assert await handlers._drop_repeated_intro(db, flow.s, cid, STORE, INTRO, "Tem tinta?") == INTRO


@pytest.mark.parametrize("other", ["b2b-sales", "azusa-church", "pessoal-teste"])
async def test_mensagem_de_outra_instancia_nao_conta(flow, other):
    cid = await _seed_outbound(flow, instance=other)
    async with flow.sessions() as db:
        assert await handlers._drop_repeated_intro(db, flow.s, cid, STORE, INTRO, "Tem tinta?") == INTRO


@pytest.mark.parametrize("pergunta", [
    "Quem é você?", "quem e vc", "Com quem eu falo?", "Você é um robô?", "isso é um bot?", "vc é humano?", "Estou falando com uma pessoa?",
    "Qual é o seu nome?", "é um robô?",
])
async def test_pergunta_de_identidade_mantem_a_apresentacao(flow, pergunta):
    cid = await _seed_outbound(flow)
    async with flow.sessions() as db:
        assert await handlers._drop_repeated_intro(db, flow.s, cid, STORE, INTRO, pergunta) == INTRO


@pytest.mark.parametrize("pergunta", ["Tem tinta branca?", "Quero 2 latas", "Quem entrega em Mauá?", "Você tem rolo de lã?"])
async def test_pergunta_comum_continua_sem_apresentacao(flow, pergunta):
    cid = await _seed_outbound(flow)
    async with flow.sessions() as db:
        assert await handlers._drop_repeated_intro(db, flow.s, cid, STORE, INTRO, pergunta) == "Temos a tinta, sim."


async def test_pelo_handler_quem_e_voce_recebe_a_apresentacao_mesmo_com_bot_ja_tendo_falado(flow, monkeypatch):
    from agents.executor import AgentResult

    async def run(*a, **k):
        return AgentResult(reply=INTRO, steps=[])
    monkeypatch.setattr("orchestrator.service.ai_orchestrator.run", run)
    cid, mid = await _msg(flow, "Quem é você?", age_seconds=5, instance=STORE, phone="5511999992200")
    async with flow.sessions() as db:
        db.add(Message(contact_id=cid, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType.TEXT, content="oi", whatsapp_instance=STORE))
        await db.commit()
    await _run(flow, cid, mid, STORE)
    assert [j.payload["content"] for j in await _jobs(flow) if j.payload["to"] == "5511999992200"] == [INTRO]
