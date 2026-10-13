"""API de revisão de entregas incertas (somente admin): inspecionar e ACEITAR a incerteza (`closed_unknown`) sem reenviar.

Contrato exercitado: papel de administrador; escopo explícito (contato + instância); revisão esperada como inteiro estrito;
confirmação `no_resend_confirmation` como booleano `true`; motivo substantivo; campos extras (recibo, ator, resultado) recusados;
ator sempre o autenticado; uma única transação; conflito (revisão antiga, envio não finalizado, já resolvido) sem gravar nada;
nenhuma chamada ao provedor de WhatsApp."""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from auth.jwt import create_access_token
from auth.password import hash_password
from models.contact import Contact
from models.user import User, UserRole
from services import conversation_control
from tests.test_whatsapp_send_queue_retry import _migrate_control_tables_sync

INSTANCE = "MARQUESCOLOR"
KEY = "send-job:42"
REASON = "Conferido no aparelho: sem confirmação de entrega"


@pytest.fixture
async def sessions(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(_migrate_control_tables_sync)
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _user(sessions, email, role):
    async with sessions() as db:
        u = User(email=email, full_name=email, hashed_password=hash_password("testpass123"), role=role, is_active=True)
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


@pytest.fixture
async def admin(sessions):
    return await _user(sessions, "admin@example.com", UserRole.ADMIN)


@pytest.fixture
def admin_h(admin):
    return {"Authorization": f"Bearer {create_access_token(str(admin.id))}"}


@pytest.fixture
async def user_h(sessions):
    u = await _user(sessions, "user@example.com", UserRole.USER)
    return {"Authorization": f"Bearer {create_access_token(str(u.id))}"}


@pytest.fixture(autouse=True)
def no_provider_calls(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a revisão de entrega nunca chama o provedor de WhatsApp")
    monkeypatch.setattr("providers.whatsapp.factory.get_whatsapp_provider", boom)
    monkeypatch.setattr("api.whatsapp.get_whatsapp_provider", boom)


async def _contact(sessions, phone="5511999990000"):
    async with sessions() as db:
        c = Contact(name="C", phone=phone, preferences={})
        db.add(c)
        await db.commit()
        return c.id


async def _ambiguous_send(sessions, contact_id, *, finished=True, key=KEY):
    """Reserva de envio incerta: reservada, transporte chamado e SEM recibo (`needs_review`, transport_finished)."""
    async with sessions() as db:
        rev = (await conversation_control.snapshot(db, contact_id, INSTANCE))["revision"]
        assert await conversation_control.claim_send(db, contact_id, INSTANCE, rev, key) == "claimed"
        if finished:
            await conversation_control.finish_send(db, key, None)
        await db.commit()
        return (await conversation_control.snapshot(db, contact_id, INSTANCE))["revision"]


def _body(_contact_id, revision, **over):
    body = {"contact_id": _contact_id, "instance": INSTANCE, "kind": "send", "key": KEY, "expected_revision": revision,
            "reason": REASON, "no_resend_confirmation": True}
    body.update(over)
    return body


async def _state(sessions, contact_id):
    async with sessions() as db:
        intent = (await db.execute(text("SELECT status FROM conversation_send_intents WHERE id=:k"), {"k": KEY})).scalar()
        control = await conversation_control.snapshot(db, contact_id, INSTANCE)
        audits = (await db.execute(text("SELECT action, actor_id, reason FROM conversation_control_audit WHERE action='close_unknown'"))).all()
    return intent, control, audits


# ----------------------------------------------------------------------------------------------------- autenticação e papel
async def test_rotas_exigem_autenticacao_e_papel_de_admin(client, sessions, user_h):
    cid = await _contact(sessions)
    q = {"contact_id": cid, "instance": INSTANCE, "kind": "send", "key": KEY}
    assert (await client.get("/api/whatsapp/deliveries", params=q)).status_code == 401
    assert (await client.post("/api/whatsapp/deliveries/close-unknown", json=_body(cid, 0))).status_code == 401
    assert (await client.get("/api/whatsapp/deliveries", params=q, headers=user_h)).status_code == 403
    assert (await client.post("/api/whatsapp/deliveries/close-unknown", json=_body(cid, 0), headers=user_h)).status_code == 403


# ----------------------------------------------------------------------------------------------------- inspeção
async def test_inspecao_devolve_metadados_do_escopo(client, sessions, admin_h):
    cid = await _contact(sessions)
    rev = await _ambiguous_send(sessions, cid)
    r = await client.get("/api/whatsapp/deliveries", params={"contact_id": cid, "instance": INSTANCE, "kind": "send", "key": KEY}, headers=admin_h)
    assert r.status_code == 200
    body = r.json()
    assert body["intent"]["status"] == "needs_review" and body["intent"]["transport_finished"] is True and body["intent"]["receipt_id"] is None
    assert body["control"]["revision"] == rev


async def test_reserva_de_outro_escopo_responde_404_igual_a_inexistente(client, sessions, admin_h):
    cid, other = await _contact(sessions), await _contact(sessions, "5511999991111")
    await _ambiguous_send(sessions, cid)
    for params in ({"contact_id": other, "instance": INSTANCE, "kind": "send", "key": KEY},          # outro contato
                   {"contact_id": cid, "instance": "OUTRA", "kind": "send", "key": KEY},             # outra instância
                   {"contact_id": cid, "instance": INSTANCE, "kind": "send", "key": "send-job:999"}):  # inexistente
        r = await client.get("/api/whatsapp/deliveries", params=params, headers=admin_h)
        assert r.status_code == 404 and r.json()["detail"] == "delivery intent not found"


@pytest.mark.parametrize("kind, key", [("anything", "valid"), ("send", "../other"), ("alert", "key/other"), ("send", ""), ("send", "a b"), ("send", "x" * 300)])
async def test_tipo_ou_chave_invalidos_sao_recusados(client, sessions, admin_h, kind, key):
    cid = await _contact(sessions)
    r = await client.get("/api/whatsapp/deliveries", params={"contact_id": cid, "instance": INSTANCE, "kind": kind, "key": key}, headers=admin_h)
    assert r.status_code == 422
    r = await client.post("/api/whatsapp/deliveries/close-unknown", json=_body(cid, 0, kind=kind, key=key), headers=admin_h)
    assert r.status_code == 422


# ----------------------------------------------------------------------------------------------------- fechamento
async def test_fechamento_usa_o_ator_autenticado_e_grava_tudo_numa_transacao(client, sessions, admin, admin_h):
    cid = await _contact(sessions)
    rev = await _ambiguous_send(sessions, cid)
    r = await client.post("/api/whatsapp/deliveries/close-unknown", json=_body(cid, rev), headers=admin_h)
    assert r.status_code == 200 and r.json()["intent"]["status"] == "closed_unknown"
    intent, control, audits = await _state(sessions, cid)
    assert intent == "closed_unknown"
    assert control["paused"] is True and control["revision"] == rev + 1 and control["inflight"] is None   # pausa; retomar é ação separada
    assert [(a[0], a[1], a[2]) for a in audits] == [("close_unknown", admin.id, REASON)]               # ator = o autenticado


@pytest.mark.parametrize("extra", [{"receipt_id": "unverified-receipt"}, {"actor_id": 123}, {"status": "sent"}, {"delivered": True}])
async def test_cliente_nao_pode_informar_recibo_ator_ou_resultado(client, sessions, admin_h, extra):
    cid = await _contact(sessions)
    rev = await _ambiguous_send(sessions, cid)
    r = await client.post("/api/whatsapp/deliveries/close-unknown", json=_body(cid, rev, **extra), headers=admin_h)
    assert r.status_code == 422
    intent, control, audits = await _state(sessions, cid)
    assert intent == "needs_review" and control["paused"] is False and audits == []


@pytest.mark.parametrize("value", ["true", 1, None, False, "yes", 0])
async def test_confirmacao_de_nao_reenvio_e_booleano_estrito(client, sessions, admin_h, value):
    cid = await _contact(sessions)
    rev = await _ambiguous_send(sessions, cid)
    r = await client.post("/api/whatsapp/deliveries/close-unknown", json=_body(cid, rev, no_resend_confirmation=value), headers=admin_h)
    assert r.status_code == 422 and (await _state(sessions, cid))[0] == "needs_review"


async def test_confirmacao_ausente_e_recusada(client, sessions, admin_h):
    cid = await _contact(sessions)
    rev = await _ambiguous_send(sessions, cid)
    body = _body(cid, rev)
    del body["no_resend_confirmation"]
    assert (await client.post("/api/whatsapp/deliveries/close-unknown", json=body, headers=admin_h)).status_code == 422


@pytest.mark.parametrize("field, value", [("instance", ""), ("instance", "   "), ("expected_revision", True), ("expected_revision", "1"),
                                          ("expected_revision", 1.0), ("expected_revision", -1), ("reason", "short"), ("reason", "        "),
                                          ("reason", "x" * 501), ("contact_id", True), ("contact_id", 0)])
async def test_escopo_revisao_e_motivo_explicitos_e_estritos(client, sessions, admin_h, field, value):
    cid = await _contact(sessions)
    rev = await _ambiguous_send(sessions, cid)
    r = await client.post("/api/whatsapp/deliveries/close-unknown", json=_body(cid, rev, **{field: value}), headers=admin_h)
    assert r.status_code == 422
    intent, control, audits = await _state(sessions, cid)
    assert intent == "needs_review" and control["paused"] is False and audits == []        # nada foi gravado


# ----------------------------------------------------------------------------------------------------- conflitos
async def test_revisao_antiga_responde_409_sem_gravar(client, sessions, admin_h):
    cid = await _contact(sessions)
    rev = await _ambiguous_send(sessions, cid)
    r = await client.post("/api/whatsapp/deliveries/close-unknown", json=_body(cid, rev + 5), headers=admin_h)     # revisão que NÃO é a atual
    assert r.status_code == 409
    intent, control, audits = await _state(sessions, cid)
    assert intent == "needs_review" and control["revision"] == rev and control["paused"] is False and audits == []


async def test_envio_nao_finalizado_nao_pode_ser_liberado(client, sessions, admin_h):
    cid = await _contact(sessions)
    rev = await _ambiguous_send(sessions, cid, finished=False)           # processo pode ter caído NO MEIO da chamada
    r = await client.post("/api/whatsapp/deliveries/close-unknown", json=_body(cid, rev), headers=admin_h)
    assert r.status_code == 409
    assert (await _state(sessions, cid))[0] == "needs_review"


async def test_segundo_fechamento_responde_409(client, sessions, admin_h):
    cid = await _contact(sessions)
    rev = await _ambiguous_send(sessions, cid)
    assert (await client.post("/api/whatsapp/deliveries/close-unknown", json=_body(cid, rev), headers=admin_h)).status_code == 200
    r = await client.post("/api/whatsapp/deliveries/close-unknown", json=_body(cid, rev + 1), headers=admin_h)
    assert r.status_code == 409
    assert len((await _state(sessions, cid))[2]) == 1                    # uma única auditoria


async def test_reserva_inexistente_ou_de_outro_contato_responde_409_sem_gravar(client, sessions, admin_h):
    cid, other = await _contact(sessions), await _contact(sessions, "5511999991111")
    rev = await _ambiguous_send(sessions, cid)
    r = await client.post("/api/whatsapp/deliveries/close-unknown", json=_body(other, 0), headers=admin_h)
    assert r.status_code == 409
    assert (await _state(sessions, cid))[0] == "needs_review" and rev == 0
