"""Recusa, pedido para não receber contatos e 'só texto' (services/store_optout.py): só frases curtas e inequívocas."""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.contact import Contact
from models.message import Message, MessageDirection, MessageMediaType
from models.store_followup import StoreFollowup
from models.store_voice import StoreVoiceSend
from services import store_optout
from utils.config import get_settings


@pytest.mark.parametrize("texto, esperado", [
    ("PARAR", "optout"), ("parar", "optout"), ("Pare de me enviar mensagens", "optout"), ("não quero mais receber mensagens", "optout"),
    ("Não quero receber mais nada, obrigado", "optout"), ("sair", "optout"), ("STOP", "optout"), ("me tire da lista", "optout"),
    ("não me envie mais", "optout"), ("Por favor, parar!", "optout"), ("não entre mais em contato", "optout"),
    ("não tenho interesse", "refusal"), ("Sem interesse.", "refusal"), ("não quero", "refusal"), ("já comprei", "refusal"),
    ("desisti", "refusal"), ("Não, obrigado", "refusal"),
    ("só texto", "text_only"), ("prefiro texto", "text_only"), ("não quero áudio", "text_only"), ("sem áudios por favor", "text_only"),
    ("me mande só texto", None),   # frase fora do vocabulário fechado: não arrisca
])
def test_classificacao_positiva(texto, esperado):
    assert store_optout.classify(texto) == esperado


@pytest.mark.parametrize("texto", [
    "", "   ", "Oi, bom dia", "Quero 2 latas de tinta branca", "Preciso parar a obra por causa da chuva, tem como adiar a entrega?",
    "não quero a lata de 18L, quero a de 3,6L", "não quero esperar até sexta", "pare na portaria por favor",
    "Vou sair às 15h, pode entregar antes?", "CONFIRMAR ABC123DEF456", "PARAR POS-VENDA",   # o pós-venda tem tratamento próprio
    "x" * 200, "não tenho interesse nessa cor, mostra outra",
])
def test_classificacao_negativa_nunca_trata_frase_longa_ou_diferente_como_opt_out(texto):
    assert store_optout.classify(texto) is None


@pytest_asyncio.fixture
async def sess(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _setup(sess, prefs=None):
    async with sess() as db:
        c = Contact(name="Cliente", phone="5511999990000", preferences=prefs or {})
        db.add(c)
        await db.flush()
        m = Message(contact_id=c.id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content="PARAR", whatsapp_instance="MARQUESCOLOR")
        db.add(m)
        await db.flush()
        from models.store import StoreCustomer
        cust = StoreCustomer(name="Cliente", phone="5511999990000", orders=[])
        db.add(cust)
        await db.flush()
        fu = StoreFollowup(dedupe_key="quote_resume:T1", kind="quote_resume", contact_id=c.id, customer_id=cust.id, instance="MARQUESCOLOR",
                           origin_type="store_quote", origin_id="T1", reason="r", due_at=datetime.now(timezone.utc), history=[], snapshot={})
        vs = StoreVoiceSend(dedupe_key="voice:reply:1", kind="reply", contact_id=c.id, instance="MARQUESCOLOR", source_message_id=m.id,
                            status="queued", script_text="oi", history=[])
        db.add_all([fu, vs])
        await db.commit()
        return c.id, m.id


async def test_opt_out_marca_cancela_acompanhamentos_e_audios_e_confirma(sess):
    cid, mid = await _setup(sess)
    async with sess() as db:
        c, m = await db.get(Contact, cid), await db.get(Message, mid)
        reply = await store_optout.handle_inbound(db, c, m)
    assert reply == store_optout.ACK_OPTOUT
    async with sess() as db:
        c = await db.get(Contact, cid)
        assert c.preferences["store_contact_opt_out"] is True and c.preferences["store_followup_opt_out"] is True
        assert store_optout.is_blocked(c) == "cliente pediu para não receber contatos"
        fu = (await db.scalars(select(StoreFollowup))).one()
        vs = (await db.scalars(select(StoreVoiceSend))).one()
        assert (fu.status, vs.status) == ("cancelled", "cancelled") and "não receber" in fu.cancel_reason


async def test_recusa_pausa_por_um_periodo_sem_opt_out_permanente(sess):
    cid, mid = await _setup(sess)
    async with sess() as db:
        c, m = await db.get(Contact, cid), await db.get(Message, mid)
        m.content = "não tenho interesse"
        assert await store_optout.handle_inbound(db, c, m) == store_optout.ACK_REFUSAL
    async with sess() as db:
        c = await db.get(Contact, cid)
        assert "store_contact_opt_out" not in c.preferences
        assert store_optout.is_blocked(c) == "cliente recusou recentemente"
        until = datetime.fromisoformat(c.preferences["store_followup_paused_until"])
        assert abs((until - datetime.now(timezone.utc)).days - get_settings().store_followup_refusal_cooldown_days) <= 1
        assert (await db.scalars(select(StoreFollowup))).one().status == "cancelled"
        # passado o período, volta a poder receber
        assert store_optout.is_blocked(c, datetime.now(timezone.utc) + timedelta(days=get_settings().store_followup_refusal_cooldown_days + 1)) is None


async def test_so_texto_nao_cancela_acompanhamentos_mas_cancela_audio(sess):
    cid, mid = await _setup(sess)
    async with sess() as db:
        c, m = await db.get(Contact, cid), await db.get(Message, mid)
        m.content = "só texto"
        assert await store_optout.handle_inbound(db, c, m) == store_optout.ACK_TEXT_ONLY
    async with sess() as db:
        c = await db.get(Contact, cid)
        assert c.preferences["reply_mode"] == "texto" and c.preferences["voice_opt_out"] is True and store_optout.is_blocked(c) is None
        assert (await db.scalars(select(StoreFollowup))).one().status == "scheduled"
        assert (await db.scalars(select(StoreVoiceSend))).one().status == "cancelled"


async def test_mensagem_comum_nao_toca_em_nada(sess):
    cid, mid = await _setup(sess)
    async with sess() as db:
        c, m = await db.get(Contact, cid), await db.get(Message, mid)
        m.content = "Quero 2 latas de tinta branca"
        assert await store_optout.handle_inbound(db, c, m) is None
    async with sess() as db:
        assert (await db.get(Contact, cid)).preferences == {}
        assert (await db.scalars(select(StoreFollowup))).one().status == "scheduled"
