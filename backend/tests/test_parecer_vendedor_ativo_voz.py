# ruff: noqa: F811
"""Regressões do parecer de 12/10/2026 (parte da VOZ): contrato real do serviço de voz para o roteiro final e atualidade da
resposta do cliente no ponto exato da reserva. Worker e handlers reais; só o transporte e o serviço de voz são simulados."""
import hashlib

from sqlalchemy import text

from models.message import Message, MessageDirection, MessageMediaType
from services import conversation_control, voice_client
from tests import test_store_voice as tv
from tests.test_store_voice import STORE, env  # noqa: F401 -- fixture do ambiente de voz
from tests.test_parecer_vendedor_ativo import REPORT_REPLY, SERVICE_LIMIT


async def test_pipeline_com_o_contrato_real_do_servico_aceita_o_roteiro_final(env, monkeypatch):
    """O simulador recusa (413) qualquer texto acima do limite do serviço real: o roteiro final tem de passar pelo contrato."""
    async def contract(text, request_id):
        assert len(text) <= SERVICE_LIMIT, f"serviço de voz recusaria com 413: {len(text)} caracteres"
        return voice_client.VoiceAudio(tv.AUDIO, hashlib.sha256(tv.AUDIO).hexdigest(), 2.0, "fake-engine", "rev", "r" * 64, "A1")
    monkeypatch.setattr(voice_client, "synthesize", contract)
    cid, mid = await tv.seed(env)
    await tv.queue_text(env, mid, reply=REPORT_REPLY)
    await tv.run_all()
    (row,) = await tv.rows(env)
    assert row.status == "sent" and len(row.script_text) <= SERVICE_LIMIT


# =====================================================================================================================
# P2 — uma resposta do cliente confirmada entre a última conferência e a reserva bloqueia a voz
# =====================================================================================================================
async def test_resposta_entre_a_conferencia_final_e_a_reserva_bloqueia_a_voz(env, monkeypatch):
    cid, mid = await tv.seed(env)
    real = conversation_control.reserve_plain_send

    async def reserve_after_customer_writes(db, contact_id, instance, intent_id, guard=None):
        if intent_id.startswith("voice-send:"):
            async with env.sessions() as other:                 # confirmada ANTES da reserva real, DEPOIS da conferência anterior
                other.add(Message(contact_id=cid, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT,
                                  content="espera, mudei de ideia", whatsapp_instance=STORE))
                await other.commit()
        return await real(db, contact_id, instance, intent_id, guard=guard)
    monkeypatch.setattr(conversation_control, "reserve_plain_send", reserve_after_customer_writes)
    await tv.queue_text(env, mid)
    await tv.run_all()
    (row,) = await tv.rows(env)
    assert row.status == "cancelled" and "cliente respondeu" in row.reason and "na reserva" in row.reason
    assert env.voice.calls == []
    async with env.sessions() as db:
        n = (await db.execute(text("SELECT count(*) FROM conversation_send_intents WHERE id LIKE 'voice-send:%'"))).scalar()
        assert n == 0                                          # nada reservado


async def test_voz_sem_resposta_nova_continua_enviando(env):
    cid, mid = await tv.seed(env)
    await tv.queue_text(env, mid)
    await tv.run_all()
    assert (await tv.rows(env))[0].status == "sent" and len(env.voice.calls) == 1


