"""PATCH /api/contacts/{id} e `preferences` (C11): a rota MESCLA sob trava e protege o opt-out; nunca substitui o dicionário.

Antes: o PATCH substituía `preferences` inteiro; um payload vazio ou antigo apagava o PARAR já registrado, sem concorrência."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.contact import Contact
from services import store_optout

OPTED_OUT = {"store_contact_opt_out": True, "store_followup_opt_out": True, "store_contact_opt_out_at": "2026-10-12T20:00:00+00:00",
             "store_contact_opt_out_message_id": 7, "reply_mode": "texto"}


async def _contact(db_engine, prefs):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions() as db:
        c = Contact(name="Cliente", phone="5511999990000", preferences=prefs)
        db.add(c)
        await db.commit()
        return c.id, sessions


async def _stored(sessions, cid):
    async with sessions() as db:
        return (await db.get(Contact, cid)).preferences


@pytest.mark.parametrize("payload", [{"preferences": {}}, {"preferences": None}, {"name": "Novo nome"}])
async def test_payload_vazio_ou_sem_preferencias_nao_apaga_o_opt_out(client, auth_headers, db_engine, payload):
    cid, sessions = await _contact(db_engine, dict(OPTED_OUT))
    r = await client.patch(f"/api/contacts/{cid}", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert await _stored(sessions, cid) == OPTED_OUT


async def test_payload_antigo_sem_as_flags_mescla_e_preserva_o_opt_out(client, auth_headers, db_engine):
    cid, sessions = await _contact(db_engine, dict(OPTED_OUT))
    r = await client.patch(f"/api/contacts/{cid}", json={"preferences": {"cor": "azul", "reply_mode": "audio"}}, headers=auth_headers)
    assert r.status_code == 200
    prefs = await _stored(sessions, cid)
    assert prefs["store_contact_opt_out"] is True and prefs["store_followup_opt_out"] is True and prefs["cor"] == "azul" and prefs["reply_mode"] == "audio"
    assert r.json()["preferences"] == prefs


@pytest.mark.parametrize("bad", [
    {"store_contact_opt_out": False}, {"store_followup_opt_out": False}, {"store_contact_opt_out": None},
    {"store_contact_opt_out_at": "2020-01-01T00:00:00+00:00"}, {"store_contact_opt_out_message_id": 1}, {"store_followup_paused_until": "2020-01-01"},
])
async def test_tentativa_de_afrouxar_chave_protegida_e_recusada_e_nada_do_payload_e_gravado(client, auth_headers, db_engine, bad):
    cid, sessions = await _contact(db_engine, {**OPTED_OUT, "store_followup_paused_until": "2026-12-01T00:00:00+00:00"})
    before = await _stored(sessions, cid)
    r = await client.patch(f"/api/contacts/{cid}", json={"name": "Outro", "preferences": {"cor": "azul", **bad}}, headers=auth_headers)
    assert r.status_code == 422 and "protegidas" in r.json()["detail"]
    assert await _stored(sessions, cid) == before                                  # nem a chave comum do mesmo payload
    async with sessions() as db:
        assert (await db.get(Contact, cid)).name == "Cliente"                      # a requisição inteira foi recusada


async def test_round_trip_com_os_mesmos_valores_protegidos_e_aceito(client, auth_headers, db_engine):
    cid, sessions = await _contact(db_engine, dict(OPTED_OUT))
    r = await client.patch(f"/api/contacts/{cid}", json={"preferences": {**OPTED_OUT, "cor": "verde"}}, headers=auth_headers)
    assert r.status_code == 200
    assert await _stored(sessions, cid) == {**OPTED_OUT, "cor": "verde"}


async def test_operador_pode_registrar_opt_out_mas_nao_remover(client, auth_headers, db_engine):
    cid, sessions = await _contact(db_engine, {"cor": "azul"})
    r = await client.patch(f"/api/contacts/{cid}", json={"preferences": {"store_contact_opt_out": True, "store_followup_opt_out": True}}, headers=auth_headers)
    assert r.status_code == 200
    contact = Contact(preferences=await _stored(sessions, cid))
    assert store_optout.is_blocked(contact) == "cliente pediu para não receber contatos"
    r = await client.patch(f"/api/contacts/{cid}", json={"preferences": {"store_contact_opt_out": False}}, headers=auth_headers)
    assert r.status_code == 422


async def test_alteracao_comum_e_remocao_por_null(client, auth_headers, db_engine):
    cid, sessions = await _contact(db_engine, {"cor": "azul", "tom": "formal"})
    r = await client.patch(f"/api/contacts/{cid}", json={"preferences": {"cor": "verde", "tom": None, "novo": 1}}, headers=auth_headers)
    assert r.status_code == 200 and await _stored(sessions, cid) == {"cor": "verde", "novo": 1}


async def test_contato_inexistente_continua_404(client, auth_headers):
    assert (await client.patch("/api/contacts/99999", json={"preferences": {"a": 1}}, headers=auth_headers)).status_code == 404


async def test_api_apos_parar_com_objeto_antigo_sequencial(client, auth_headers, db_engine):
    """PARAR confirma e, DEPOIS, um formulário antigo (carregado antes do PARAR) é enviado: o opt-out sobrevive."""
    from models.message import Message, MessageDirection, MessageMediaType
    from tests.test_whatsapp_send_queue_retry import _migrate_control_tables_sync
    async with db_engine.begin() as conn:
        await conn.run_sync(_migrate_control_tables_sync)
    cid, sessions = await _contact(db_engine, {"cor": "azul"})
    async with sessions() as db:
        c = await db.get(Contact, cid)
        m = Message(contact_id=cid, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content="PARAR", whatsapp_instance="MARQUESCOLOR")
        db.add(m)
        await db.flush()
        assert await store_optout.handle_inbound(db, c, m) == store_optout.ACK_OPTOUT
    r = await client.patch(f"/api/contacts/{cid}", json={"preferences": {"cor": "azul"}}, headers=auth_headers)    # "formulário antigo"
    assert r.status_code == 200
    assert (await _stored(sessions, cid))["store_contact_opt_out"] is True


async def test_mark_opt_out_grava_as_chaves_permanentes(db_engine):
    from tests.test_whatsapp_send_queue_retry import _migrate_control_tables_sync
    async with db_engine.begin() as conn:
        await conn.run_sync(_migrate_control_tables_sync)
    cid, sessions = await _contact(db_engine, {"cor": "azul"})
    async with sessions() as db_a, sessions() as db_b:
        stale = await db_b.get(Contact, cid)
        await db_a.get(Contact, cid)
        await store_optout.mark_opt_out(db_a, await db_a.get(Contact, cid), instance="MARQUESCOLOR", message_id=5)
        await db_a.commit()
        await store_optout.mark_opt_out(db_b, stale, instance="MARQUESCOLOR", message_id=6)        # objeto defasado: relê e preserva
        await db_b.commit()
    prefs = await _stored(sessions, cid)
    assert prefs["cor"] == "azul" and prefs["store_contact_opt_out"] is True and prefs["store_contact_opt_out_message_id"] == 6


@pytest.mark.parametrize("fake", [1, 1.0, "true", "True", [True], {"v": True}])
async def test_valor_equivalente_mas_de_outro_tipo_nao_remove_o_bloqueio(client, auth_headers, db_engine, fake):
    """Contato com APENAS store_followup_opt_out=true: enviar a flag como 1/1.0/"true" junto com uma preferência comum é recusado
    (422), nada é gravado e o booleano original e o bloqueio efetivo permanecem."""
    cid, sessions = await _contact(db_engine, {"store_followup_opt_out": True})
    r = await client.patch(f"/api/contacts/{cid}", json={"name": "Outro", "preferences": {"store_followup_opt_out": fake, "cor": "azul"}}, headers=auth_headers)
    assert r.status_code == 422 and "store_followup_opt_out" in r.json()["detail"]
    prefs = await _stored(sessions, cid)
    assert prefs == {"store_followup_opt_out": True} and prefs["store_followup_opt_out"] is True
    assert store_optout.is_blocked(Contact(preferences=prefs)) == "cliente pediu para não receber contatos"
    async with sessions() as db:
        assert (await db.get(Contact, cid)).name == "Cliente"


@pytest.mark.parametrize("fake", [1, 1.0, "true"])
async def test_numero_como_flag_nova_em_contato_sem_opt_out_tambem_e_recusado(client, auth_headers, db_engine, fake):
    cid, sessions = await _contact(db_engine, {"cor": "azul"})
    r = await client.patch(f"/api/contacts/{cid}", json={"preferences": {"store_contact_opt_out": fake}}, headers=auth_headers)
    assert r.status_code == 422
    assert await _stored(sessions, cid) == {"cor": "azul"}                       # nem o número nem nada foi gravado


async def test_reenvio_com_o_mesmo_booleano_preserva_o_booleano_e_aplica_a_outra_preferencia(client, auth_headers, db_engine):
    cid, sessions = await _contact(db_engine, {"store_followup_opt_out": True})
    r = await client.patch(f"/api/contacts/{cid}", json={"preferences": {"store_followup_opt_out": True, "cor": "azul"}}, headers=auth_headers)
    assert r.status_code == 200
    prefs = await _stored(sessions, cid)
    assert prefs == {"store_followup_opt_out": True, "cor": "azul"} and prefs["store_followup_opt_out"] is True


async def test_operador_registra_opt_out_somente_com_booleano_verdadeiro(client, auth_headers, db_engine):
    cid, sessions = await _contact(db_engine, {})
    assert (await client.patch(f"/api/contacts/{cid}", json={"preferences": {"store_contact_opt_out": 1}}, headers=auth_headers)).status_code == 422
    assert (await client.patch(f"/api/contacts/{cid}", json={"preferences": {"store_contact_opt_out": True}}, headers=auth_headers)).status_code == 200
    assert (await _stored(sessions, cid))["store_contact_opt_out"] is True


async def test_metadado_numerico_de_tipo_diferente_tambem_e_recusado(client, auth_headers, db_engine):
    cid, sessions = await _contact(db_engine, dict(OPTED_OUT))
    r = await client.patch(f"/api/contacts/{cid}", json={"preferences": {"store_contact_opt_out_message_id": 7.0}}, headers=auth_headers)
    assert r.status_code == 422 and await _stored(sessions, cid) == OPTED_OUT
