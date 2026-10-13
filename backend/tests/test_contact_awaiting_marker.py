"""`Contact.awaiting_reply_since`: o marcador de resposta pendente do Twin é uma coluna persistida (não um atributo transitório).

Prova, em SESSÕES NOVAS do ORM: gravar, recarregar, limpar. E pelo `dispatch_inbound` real: com o Twin LIGADO o marcador é gravado e a
checagem do autopiloto é agendada; com o Twin DESLIGADO (ou numa instância que não é a pessoal) o marcador não é tocado."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.contact import Contact
from models.job import Job
from providers.whatsapp.base import InboundMessage
from utils.config import get_settings
from webhooks import router as webhook_router

WHEN = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def sessions(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _contact(sessions, **kw):
    async with sessions() as db:
        c = Contact(name="C", phone="5511999995001", preferences={}, **kw)
        db.add(c)
        await db.commit()
        return c.id


async def _reload(sessions, cid):
    async with sessions() as db:
        return (await db.execute(select(Contact).where(Contact.id == cid))).scalar_one().awaiting_reply_since


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


async def test_marcador_grava_recarrega_e_limpa_em_sessoes_novas(sessions):
    cid = await _contact(sessions)
    assert await _reload(sessions, cid) is None
    async with sessions() as db:
        (await db.get(Contact, cid)).awaiting_reply_since = WHEN
        await db.commit()
    assert _aware(await _reload(sessions, cid)) == WHEN                     # sobreviveu à sessão: está na coluna
    async with sessions() as db:
        (await db.get(Contact, cid)).awaiting_reply_since = None
        await db.commit()
    assert await _reload(sessions, cid) is None


async def _dispatch(sessions, monkeypatch, *, twin, instance="darioos", personal=""):
    settings = get_settings()
    monkeypatch.setattr(settings, "auto_reply_enabled", True)
    monkeypatch.setattr(settings, "store_whatsapp_enabled", True)
    monkeypatch.setattr(settings, "whatsapp_twin_mode_enabled", twin)
    monkeypatch.setattr(settings, "evolution_personal_instance", personal)

    async def nothing(*a, **k):
        return False

    async def allowed(*a, **k):
        return True
    monkeypatch.setattr(webhook_router.contact_memory_service, "record_interaction", nothing)
    monkeypatch.setattr(webhook_router.rate_limiter, "is_allowed", allowed)
    cid = await _contact(sessions)
    inbound = InboundMessage(phone="5511999995001", text="oi, tem tinta?", external_id="E1", instance=instance, timestamp=WHEN)
    async with sessions() as db:
        contact = await db.get(Contact, cid)
        message = type("M", (), {"id": 1})()
        await webhook_router.dispatch_inbound(db, type("P", (), {"name": "evolution"})(), inbound, contact, message, "text")
        await db.commit()
    async with sessions() as db:
        jobs = [j.name for j in (await db.execute(select(Job))).scalars()]
    return cid, jobs


async def test_twin_ligado_grava_o_marcador_e_agenda_a_checagem(sessions, monkeypatch):
    cid, jobs = await _dispatch(sessions, monkeypatch, twin=True)
    assert _aware(await _reload(sessions, cid)) == WHEN
    assert "whatsapp.twin_autopilot_check" in jobs


async def test_twin_desligado_nao_toca_no_marcador(sessions, monkeypatch):
    cid, jobs = await _dispatch(sessions, monkeypatch, twin=False)
    assert await _reload(sessions, cid) is None
    assert "whatsapp.twin_autopilot_check" not in jobs


async def test_twin_ligado_mas_instancia_da_loja_nao_marca_nem_agenda(sessions, monkeypatch):
    cid, jobs = await _dispatch(sessions, monkeypatch, twin=True, instance="loja", personal="pessoal")
    assert await _reload(sessions, cid) is None
    assert "whatsapp.twin_autopilot_check" not in jobs                      # o Twin é reservado ao número pessoal
