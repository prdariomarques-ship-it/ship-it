# ruff: noqa: F811
"""Barreira de revisão dos envios comuns depois de pausa e retomada: uma resposta gerada ANTES de uma pausa/retomada não é liberada
quando a conversa é retomada (ela perdeu o contexto do atendimento humano). Handler e worker reais; transporte simulado."""
import pytest
from sqlalchemy import select, text

import jobs.handlers  # noqa: F401
from jobs.service import JobService
from models.job import Job
from services import conversation_control
from tests.test_message_age_guard import _jobs, _msg, _run, flow  # noqa: F401
from tests.test_parecer_vendedor_ativo import drain
from tests.test_store_followups import PHONE, STORE, env  # noqa: F401


async def _revision(env, cid, instance=STORE):
    async with env.sessions() as db:
        return (await conversation_control.snapshot(db, cid, instance))["revision"]


async def _enqueue(env, cid, *, revision, instance=STORE, content="Temos a tinta, sim."):
    payload = {"to": PHONE, "content": content, "instance": instance}
    if revision is not None:
        payload["control_revision"] = revision
    async with env.sessions() as db:
        return (await JobService(db).enqueue("whatsapp.send_text", payload)).id


async def _pause_resume(env, cid, instance=STORE):
    async with env.sessions() as db:
        state = await conversation_control.pause(db, cid, instance, f"h-{cid}", "humano")
        await db.commit()
        await conversation_control.resume(db, cid, instance, state["revision"], actor_id=1)
        await db.commit()


async def _contact(env, phone=PHONE):
    from models.contact import Contact
    async with env.sessions() as db:
        c = Contact(name="C", phone=phone, preferences={})
        db.add(c)
        await db.commit()
        return c.id


async def test_resposta_gerada_antes_de_pausa_e_retomada_nao_e_liberada(env):
    cid = await _contact(env)
    rev = await _revision(env, cid)
    await _enqueue(env, cid, revision=rev)
    await _pause_resume(env, cid)
    await drain()
    assert env.text.calls == []
    async with env.sessions() as db:
        assert (await db.scalars(select(Job).where(Job.name == "whatsapp.send_text"))).one().status.value == "succeeded"
        n = (await db.execute(text("SELECT count(*) FROM conversation_send_intents"))).scalar()
        assert n == 0


async def test_sem_pausa_a_resposta_sai(env):
    cid = await _contact(env)
    await _enqueue(env, cid, revision=await _revision(env, cid))
    await drain()
    assert len(env.text.calls) == 1


async def test_payload_legado_sem_revisao_continua_saindo(env):
    cid = await _contact(env)
    await _enqueue(env, cid, revision=None)
    await _pause_resume(env, cid)
    await drain()
    assert len(env.text.calls) == 1                      # compatibilidade: jobs antigos não têm o campo


async def test_so_pausa_continua_barrando_pela_pausa(env):
    cid = await _contact(env)
    await _enqueue(env, cid, revision=await _revision(env, cid))
    async with env.sessions() as db:
        await conversation_control.pause(db, cid, STORE, "h1", "humano")
        await db.commit()
    await drain()
    assert env.text.calls == []


async def test_pausa_e_retomada_em_outra_instancia_nao_barra(env):
    cid = await _contact(env)
    await _enqueue(env, cid, revision=await _revision(env, cid))
    await _pause_resume(env, cid, instance="outra-instancia")
    await drain()
    assert len(env.text.calls) == 1


@pytest.mark.parametrize("bad", ["3", 3.0, True, None])
async def test_revisao_de_tipo_estranho_e_ignorada_como_ausente(env, bad):
    cid = await _contact(env)
    payload = {"to": PHONE, "content": "oi", "instance": STORE, "control_revision": bad}
    async with env.sessions() as db:
        await JobService(db).enqueue("whatsapp.send_text", payload)
    await _pause_resume(env, cid)
    await drain()
    assert len(env.text.calls) == 1                      # só um int de verdade vale; nada de comparação frouxa


async def test_o_handler_de_entrada_grava_a_revisao_no_job_de_resposta(flow, monkeypatch):
    from agents.executor import AgentResult
    async def run(*a, **k):
        return AgentResult(reply="Temos sim.", steps=[])
    monkeypatch.setattr("orchestrator.service.ai_orchestrator.run", run)
    cid, mid = await _msg(flow, "Tem tinta?", age_seconds=10, instance=STORE, phone="5511999993001")
    await _pause_resume(flow, cid)                        # revisão passa a 2 ANTES do processamento
    await _run(flow, cid, mid, STORE)
    (job,) = [j for j in await _jobs(flow) if j.payload["to"] == "5511999993001"]
    assert job.payload["control_revision"] == await _revision(flow, cid) == 2


async def test_fim_a_fim_pausa_retomada_depois_do_processamento_barra_o_envio(flow, monkeypatch):
    from agents.executor import AgentResult

    async def run(*a, **k):
        return AgentResult(reply="Temos sim.", steps=[])
    monkeypatch.setattr("orchestrator.service.ai_orchestrator.run", run)
    cid, mid = await _msg(flow, "Tem tinta?", age_seconds=10, instance=STORE, phone="5511999993002")
    await _run(flow, cid, mid, STORE)                     # resposta gerada e enfileirada
    await _pause_resume(flow, cid)                        # humano assume e devolve
    await drain()
    assert flow.text.calls == []


@pytest.mark.parametrize("instance, phone", [("b2b-sales", "5511999993011"), ("azusa-church", "5511999993012")])
async def test_b2b_e_azusa_tambem_carregam_a_revisao_e_sao_barrados(flow, monkeypatch, instance, phone):
    from agents.executor import AgentResult

    async def run(*a, **k):
        return AgentResult(reply="Posso ajudar com isso.", steps=[])
    monkeypatch.setattr("orchestrator.service.ai_orchestrator.run", run)
    cid, mid = await _msg(flow, "Olá, preciso de ajuda", age_seconds=10, instance=instance, phone=phone)
    await _run(flow, cid, mid, instance)
    (job,) = [j for j in await _jobs(flow) if j.payload["to"] == phone]
    assert job.payload["control_revision"] == await _revision(flow, cid, instance)
    await _pause_resume(flow, cid, instance)
    await drain()
    assert flow.text.calls == []
