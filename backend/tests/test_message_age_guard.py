# ruff: noqa: F811
"""Bloqueio de mensagens antigas nos fluxos de agentes (Loja, B2B, Azusa, Twin/pessoal): pelo handler real de mensagem recebida.

Limiar `auto_reply_max_message_age_seconds` (0 = desligado). PARAR/recusa/só texto antigos continuam sendo honrados."""
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import jobs.handlers  # noqa: F401
from jobs.handlers import process_inbound_whatsapp_message
from models.contact import Contact
from models.job import Job
from models.message import Message, MessageDirection, MessageMediaType
from services import store_optout
from tests.test_store_followups import STORE, env  # noqa: F401

LIMIT = 1800


class Reached(Exception):
    """O fluxo passou da checagem de idade e chegou ao agente."""


async def _owner(self):
    class U:
        id = 1
    return U()


@pytest.fixture
def flow(env, monkeypatch):
    monkeypatch.setattr(env.s, "auto_reply_max_message_age_seconds", LIMIT)
    monkeypatch.setattr("repositories.user.UserRepository.get_first_admin", _owner)
    stub = types.ModuleType("services.store_aftercare")      # o pós-venda real não faz parte desta linha de código
    stub.is_stop_request = lambda _c: False                   # type: ignore[attr-defined]
    stub.stop_followups = None                                # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "services.store_aftercare", stub)
    sales = types.ModuleType("services.store_sales")          # idem: módulo de produção ausente desta linha de código
    sales.confirmation_code = lambda _c: None                 # type: ignore[attr-defined]
    sales.confirm_quote = None                                # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "services.store_sales", sales)

    async def boom(*a, **k):
        raise Reached()
    monkeypatch.setattr("orchestrator.service.ai_orchestrator.run", boom)
    monkeypatch.setattr("orchestrator.pipeline.cognitive_pipeline.process", boom)
    return env


async def _msg(env, content, *, age_seconds, instance, phone):
    async with env.sessions() as db:
        c = Contact(name="C", phone=phone, preferences={})
        db.add(c)
        await db.flush()
        m = Message(contact_id=c.id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content=content,
                    whatsapp_instance=instance, created_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds))
        db.add(m)
        await db.commit()
        return c.id, m.id


async def _run(env, cid, mid, instance):
    async with env.sessions() as db:
        await process_inbound_whatsapp_message(db, {"contact_id": cid, "message_id": mid, "instance": instance})


async def _jobs(env):
    async with env.sessions() as db:
        return list((await db.scalars(select(Job).where(Job.name == "whatsapp.send_text"))).all())


@pytest.mark.parametrize("instance, phone", [(STORE, "5511999990001"), ("b2b-sales", "5511999990002"), ("azusa-church", "5511999990003"),
                                              ("pessoal-teste", "5511999990004")])
async def test_mensagem_antiga_nao_chega_ao_agente_e_a_recente_chega(flow, instance, phone):
    cid, mid = await _msg(flow, "Quero 2 latas de tinta", age_seconds=LIMIT + 60, instance=instance, phone=phone)
    await _run(flow, cid, mid, instance)                                   # antiga: silêncio, sem exceção do agente
    assert await _jobs(flow) == []
    cid, mid = await _msg(flow, "Quero 2 latas de tinta", age_seconds=30, instance=instance, phone=phone[:-1] + "9")
    with pytest.raises(Reached):                                           # recente: o agente é chamado
        await _run(flow, cid, mid, instance)


async def test_limiar_zero_desliga_a_guarda(flow, monkeypatch):
    monkeypatch.setattr(flow.s, "auto_reply_max_message_age_seconds", 0)
    cid, mid = await _msg(flow, "Quero tinta", age_seconds=86400, instance=STORE, phone="5511999990005")
    with pytest.raises(Reached):
        await _run(flow, cid, mid, STORE)


async def test_parar_antigo_ainda_e_honrado(flow):
    cid, mid = await _msg(flow, "PARAR", age_seconds=LIMIT * 10, instance=STORE, phone="5511999990006")
    await _run(flow, cid, mid, STORE)
    async with flow.sessions() as db:
        prefs = (await db.get(Contact, cid)).preferences
    assert prefs["store_contact_opt_out"] is True
    assert [j.payload["content"] for j in await _jobs(flow)] == [store_optout.ACK_OPTOUT]


async def test_mensagem_sem_data_confiavel_nao_e_bloqueada(flow):
    from jobs.handlers import _message_too_old
    assert _message_too_old(flow.s, types.SimpleNamespace(created_at=None)) is False
