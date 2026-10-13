"""Revisão de entregas incertas ponta a ponta pelo WORKER REAL: envio comum → retorno sem recibo → fechamento administrativo.

O envio comum usa `reserve_plain_send`, que NÃO grava a marca `inflight` da conversa. O fechamento (`close_unknown`) precisa
funcionar para essa reserva, recusar antes de o transporte terminar e preservar qualquer reserva concorrente. Só o provedor de
WhatsApp é simulado."""
import asyncio

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

import jobs.handlers  # noqa: F401
from auth.jwt import create_access_token
from auth.password import hash_password
from jobs.service import JobService
from jobs.worker import JobWorker
from models.contact import Contact
from models.user import User, UserRole
from providers.whatsapp.base import WhatsAppProviderError
from services import conversation_control
from tests.test_whatsapp_send_queue_retry import _migrate_control_tables_sync
from utils.config import get_settings

INSTANCE = "MARQUESCOLOR"
PHONE = "5511999990000"
REASON = "Conferido no aparelho: sem confirmação de entrega"


class Provider:
    name = "evolution"
    default_instance = INSTANCE

    def __init__(self, outcome=None, gate=None, entered=None):
        self.calls, self.outcome, self.gate, self.entered = [], outcome, gate, entered

    async def send_text(self, to, content, instance=None):
        self.calls.append((to, content))
        if self.entered is not None:
            self.entered.set()
        if self.gate is not None:
            await self.gate.wait()
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome if self.outcome is not None else {}          # SEM recibo: resultado incerto


@pytest.fixture
async def world(db_engine, monkeypatch):
    async with db_engine.begin() as conn:
        await conn.run_sync(_migrate_control_tables_sync)
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("jobs.worker.async_session_factory", sessions)
    monkeypatch.setattr(get_settings(), "jobs_retry_backoff_seconds", 0)

    class W:
        pass
    w = W()
    w.sessions = sessions
    async with sessions() as db:
        admin = User(email="admin@example.com", full_name="A", hashed_password=hash_password("testpass123"), role=UserRole.ADMIN, is_active=True)
        contact = Contact(name="C", phone=PHONE, preferences={})
        db.add_all([admin, contact])
        await db.commit()
        w.admin_id, w.contact_id = admin.id, contact.id
    w.headers = {"Authorization": f"Bearer {create_access_token(str(w.admin_id))}"}

    def use(provider):
        monkeypatch.setattr("jobs.handlers.get_whatsapp_provider", lambda: provider)
        return provider
    w.use = use
    return w


async def _enqueue(w, content="Temos a tinta, sim."):
    async with w.sessions() as db:
        return (await JobService(db).enqueue("whatsapp.send_text", {"to": PHONE, "content": content, "instance": INSTANCE})).id


async def _drain(rounds=8):
    for _ in range(rounds):
        if not await JobWorker().run_once():
            break


async def _intent(w, job_id):
    async with w.sessions() as db:
        row = (await db.execute(text("SELECT status, transport_finished, revision FROM conversation_send_intents WHERE id=:i"), {"i": f"send-job:{job_id}"})).first()
        control = await conversation_control.snapshot(db, w.contact_id, INSTANCE)
    return row, control


def _close_body(w, revision, job_id, **over):
    body = {"contact_id": w.contact_id, "instance": INSTANCE, "kind": "send", "key": f"send-job:{job_id}", "expected_revision": revision,
            "reason": REASON, "no_resend_confirmation": True}
    body.update(over)
    return body


async def _close(client, w, revision, job_id, **over):
    return await client.post("/api/whatsapp/deliveries/close-unknown", json=_close_body(w, revision, job_id, **over), headers=w.headers)


async def test_envio_comum_sem_recibo_pode_ser_fechado_pelo_administrador(client, world):
    provider = world.use(Provider())
    job_id = await _enqueue(world)
    await _drain()
    assert len(provider.calls) == 1
    row, control = await _intent(world, job_id)
    assert (row[0], bool(row[1]), row[2]) == ("needs_review", True, None)        # reserva comum: revisão nula, transporte finalizado
    assert control["inflight"] is None                                            # reserve_plain_send NÃO grava a cerca
    q = {"contact_id": world.contact_id, "instance": INSTANCE, "kind": "send", "key": f"send-job:{job_id}"}
    info = (await client.get("/api/whatsapp/deliveries", params=q, headers=world.headers)).json()
    assert info["intent"]["reservation"] == "plain" and info["intent"]["transport_finished"] is True
    r = await _close(client, world, control["revision"], job_id)
    assert r.status_code == 200 and r.json()["intent"]["status"] == "closed_unknown"
    row, control2 = await _intent(world, job_id)
    assert row[0] == "closed_unknown" and control2["paused"] is True and control2["revision"] == control["revision"] + 1
    async with world.sessions() as db:
        audit = (await db.execute(text("SELECT actor_id, reason, intent_kind, intent_key FROM conversation_control_audit WHERE action='close_unknown'"))).all()
    assert audit == [(world.admin_id, REASON, "send", f"send-job:{job_id}")]
    assert len(provider.calls) == 1                                               # fechar nunca reenvia


async def test_conversa_fica_pausada_depois_do_fechamento_e_novos_envios_nao_saem(client, world):
    provider = world.use(Provider())
    job_id = await _enqueue(world)
    await _drain()
    _, control = await _intent(world, job_id)
    assert (await _close(client, world, control["revision"], job_id)).status_code == 200
    await _enqueue(world, "outra mensagem")
    await _drain()
    assert len(provider.calls) == 1                                               # pausa: a próxima resposta automática não sai


async def test_fechamento_antes_de_o_transporte_terminar_e_recusado(client, world):
    gate, entered = asyncio.Event(), asyncio.Event()
    provider = world.use(Provider(gate=gate, entered=entered))
    job_id = await _enqueue(world)
    worker = asyncio.create_task(_drain())
    await asyncio.wait_for(entered.wait(), 10)                                    # o provedor está no meio da chamada
    row, control = await _intent(world, job_id)
    assert (row[0], bool(row[1])) == ("needs_review", False)
    refused = await _close(client, world, control["revision"], job_id)
    assert refused.status_code == 409
    assert (await _intent(world, job_id))[0][0] == "needs_review" and (await _intent(world, job_id))[1]["paused"] is False
    gate.set()
    await asyncio.wait_for(worker, 10)
    row, control = await _intent(world, job_id)
    assert bool(row[1]) is True and len(provider.calls) == 1
    assert (await _close(client, world, control["revision"], job_id)).status_code == 200      # agora sim


async def test_erro_ambiguo_de_transporte_tambem_pode_ser_aceito_sem_reenvio(client, world):
    exc = WhatsAppProviderError("evolution request failed: ReadTimeout")
    exc.__cause__ = httpx.ReadTimeout("sem resposta")
    provider = world.use(Provider(outcome=exc))
    job_id = await _enqueue(world)
    await _drain(10)
    assert len(provider.calls) == 1                                               # as retentativas da fila não reenviaram
    row, control = await _intent(world, job_id)
    assert (row[0], bool(row[1])) == ("needs_review", True)
    assert (await _close(client, world, control["revision"], job_id)).status_code == 200
    assert len(provider.calls) == 1


async def test_falha_provadamente_anterior_ao_envio_libera_a_reserva_e_nao_ha_o_que_fechar(client, world):
    exc = WhatsAppProviderError("evolution request failed: ConnectError")
    exc.__cause__ = httpx.ConnectError("recusou")
    world.use(Provider(outcome=exc))
    job_id = await _enqueue(world)
    await _drain(10)
    assert (await _intent(world, job_id))[0] is None                              # reserva liberada: pode ser repetida pela fila
    r = await _close(client, world, 0, job_id)
    assert r.status_code == 409


async def test_reserva_concorrente_de_outro_envio_e_preservada(client, world):
    world.use(Provider())
    job_id = await _enqueue(world)
    await _drain()
    async with world.sessions() as db:                                            # outro envio, com cerca (claim_send), entra DEPOIS
        rev = (await conversation_control.snapshot(db, world.contact_id, INSTANCE))["revision"]
        assert await conversation_control.claim_send(db, world.contact_id, INSTANCE, rev, "twin-send:other-1") == "claimed"
        await db.commit()
    _, control = await _intent(world, job_id)
    assert control["inflight"] == "twin-send:other-1"
    r = await _close(client, world, control["revision"], job_id)
    assert r.status_code == 200
    row, after = await _intent(world, job_id)
    assert row[0] == "closed_unknown" and after["paused"] is True
    assert after["inflight"] == "twin-send:other-1"                               # a cerca do OUTRO envio não foi limpa
    async with world.sessions() as db:
        other = (await db.execute(text("SELECT status FROM conversation_send_intents WHERE id='twin-send:other-1'"))).scalar()
    assert other == "needs_review"                                                # e a outra reserva continua intacta


async def test_reserva_com_cerca_continua_exigindo_a_cerca(client, world):
    """claim_send finalizada cuja cerca foi perdida (inflight mudou) continua recusada: o comportamento antigo foi preservado."""
    async with world.sessions() as db:
        rev = (await conversation_control.snapshot(db, world.contact_id, INSTANCE))["revision"]
        assert await conversation_control.claim_send(db, world.contact_id, INSTANCE, rev, "twin-send:f1") == "claimed"
        await conversation_control.finish_send(db, "twin-send:f1", None)
        await db.commit()
    body = {"contact_id": world.contact_id, "instance": INSTANCE, "kind": "send", "key": "twin-send:f1", "expected_revision": rev,
            "reason": REASON, "no_resend_confirmation": True}
    async with world.sessions() as db:                                            # a cerca some por fora (cenário de conflito)
        await db.execute(text("UPDATE conversation_controls SET inflight='alguem-mais' WHERE contact_id=:c"), {"c": world.contact_id})
        await db.commit()
    assert (await client.post("/api/whatsapp/deliveries/close-unknown", json=body, headers=world.headers)).status_code == 409
    async with world.sessions() as db:
        await db.execute(text("UPDATE conversation_controls SET inflight='twin-send:f1' WHERE contact_id=:c"), {"c": world.contact_id})
        await db.commit()
    r = await client.post("/api/whatsapp/deliveries/close-unknown", json=body, headers=world.headers)
    assert r.status_code == 200
    assert (await _intent(world, 0))[1]["inflight"] is None                       # a cerca DESTA reserva é limpa
