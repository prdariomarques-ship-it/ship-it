# ruff: noqa: F811  -- fixtures importadas de tests.test_whatsapp_send_queue_retry (padrão pytest) são "redefinidas" nos parâmetros
"""Complemento de test_delivery_review_worker.py: bordas do fechamento de envio comum que ele não cobre
(outros envios comuns do contato, segundo fechamento, revisão antiga sem gravar, envio já com recibo).

Caminho real dos envios comuns da fila.

Há dois tipos de reserva de envio (services/conversation_control.py):
  - COM CERCA (`claim_send`, respostas do Twin): grava `conversation_controls.inflight = <intenção>` e `revision`;
  - SIMPLES (`reserve_plain_send`, todo envio comum da fila `whatsapp.send_text`): NUNCA grava `inflight` e fica com `revision` nula.
`close_unknown` exigia `inflight == chave` para todo `kind == 'send'`; para a reserva simples isso nunca é verdade, então o
administrador recebia 409 justamente no caso que a revisão existe para resolver. Os testes de test_delivery_review_api.py criam a
reserva só com `claim_send`; aqui o percurso é o real: worker -> transporte responde sem recibo -> inspeção -> fechamento.
"""
import pytest
from sqlalchemy import text

from auth.jwt import create_access_token
from models.user import UserRole
from services import conversation_control
from tests.test_delivery_review_api import REASON, _user
from tests.test_whatsapp_send_queue_retry import (  # noqa: F401 -- fixtures e helpers do worker real
    PHONE,
    _enqueue_send,
    _job_status,
    _run_worker_until_idle,
    control_db,
    provider,
)

INSTANCE = "store"  # a instância do payload do worker nestes testes


@pytest.fixture(autouse=True)
def no_memory_work(monkeypatch):
    """O worker também persiste a mensagem e alimenta a memória do contato; isso não faz parte do que se testa aqui."""
    async def nothing(*args, **kwargs):
        return False

    monkeypatch.setattr("services.messaging.contact_memory_service.record_interaction", nothing)


@pytest.fixture
async def admin_h(control_db):
    admin = await _user(control_db, "admin-plain@example.com", UserRole.ADMIN)
    return {"Authorization": f"Bearer {create_access_token(str(admin.id))}"}


async def _contact_id(sessions, phone_suffix="999990000"):
    async with sessions() as db:
        return (await db.execute(text("SELECT id FROM contacts WHERE phone LIKE :p"), {"p": f"%{phone_suffix}"})).scalar_one()


async def _intent(sessions, key):
    async with sessions() as db:
        row = (await db.execute(
            text("SELECT status, revision, transport_finished, receipt_id FROM conversation_send_intents WHERE id=:k"), {"k": key}
        )).first()
    return None if row is None else {"status": row[0], "revision": row[1], "finished": bool(row[2]), "receipt": row[3]}


async def _control(sessions, cid):
    async with sessions() as db:
        return await conversation_control.snapshot(db, cid, INSTANCE)


async def _audits(sessions):
    async with sessions() as db:
        return (await db.execute(text("SELECT actor_id, reason, intent_kind, intent_key FROM conversation_control_audit WHERE action='close_unknown'"))).all()


def _params(cid, key):
    return {"contact_id": cid, "instance": INSTANCE, "kind": "send", "key": key}


def _close(cid, key, revision, **over):
    body = {**_params(cid, key), "expected_revision": revision, "reason": REASON, "no_resend_confirmation": True}
    body.update(over)
    return body


async def _queued_send_without_receipt(sessions, provider, content="Temos o thinner 5L, R$ 45,00."):
    """O caminho real: job enfileirado -> JobWorker -> reserve_plain_send -> transporte responde SEM recibo -> finish_send."""
    fake = provider([{}])
    job_id = await _enqueue_send(sessions, {"to": PHONE, "content": content, "instance": INSTANCE})
    await _run_worker_until_idle()
    assert await _job_status(sessions, job_id) is not None
    return fake, f"send-job:{job_id}"


async def test_fechar_um_envio_comum_nao_toca_nos_outros_envios_comuns_do_contato(control_db, provider, client, admin_h):
    _, key_a = await _queued_send_without_receipt(control_db, provider, "primeira")
    _, key_b = await _queued_send_without_receipt(control_db, provider, "segunda")
    cid = await _contact_id(control_db)
    revision = (await _control(control_db, cid))["revision"]

    closed = await client.post("/api/whatsapp/deliveries/close-unknown", json=_close(cid, key_a, revision), headers=admin_h)
    assert closed.status_code == 200
    assert (await _intent(control_db, key_a))["status"] == "closed_unknown"
    assert (await _intent(control_db, key_b))["status"] == "needs_review"          # o outro continua aguardando revisão própria


async def test_segundo_fechamento_do_envio_comum_responde_409(control_db, provider, client, admin_h):
    _, key = await _queued_send_without_receipt(control_db, provider)
    cid = await _contact_id(control_db)
    revision = (await _control(control_db, cid))["revision"]
    first = await client.post("/api/whatsapp/deliveries/close-unknown", json=_close(cid, key, revision), headers=admin_h)
    assert first.status_code == 200
    second = await client.post("/api/whatsapp/deliveries/close-unknown", json=_close(cid, key, revision + 1), headers=admin_h)
    assert second.status_code == 409


async def test_envio_comum_com_revisao_antiga_responde_409_sem_gravar(control_db, provider, client, admin_h):
    _, key = await _queued_send_without_receipt(control_db, provider)
    cid = await _contact_id(control_db)
    revision = (await _control(control_db, cid))["revision"]
    r = await client.post("/api/whatsapp/deliveries/close-unknown", json=_close(cid, key, revision + 5), headers=admin_h)
    assert r.status_code == 409
    assert (await _intent(control_db, key))["status"] == "needs_review"
    assert (await _control(control_db, cid))["paused"] is False and await _audits(control_db) == []


async def test_envio_comum_com_recibo_ja_esta_resolvido_e_nao_pode_ser_fechado(control_db, provider, client, admin_h):
    fake = provider([{"key": {"id": "EVT-OK"}}])
    job_id = await _enqueue_send(control_db, {"to": PHONE, "content": "Pedido confirmado.", "instance": INSTANCE})
    await _run_worker_until_idle()
    assert len(fake.calls) == 1
    key, cid = f"send-job:{job_id}", await _contact_id(control_db)
    assert (await _intent(control_db, key))["status"] == "sent"
    revision = (await _control(control_db, cid))["revision"]
    r = await client.post("/api/whatsapp/deliveries/close-unknown", json=_close(cid, key, revision), headers=admin_h)
    assert r.status_code == 409
