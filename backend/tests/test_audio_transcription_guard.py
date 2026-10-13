"""A06 — áudio recebido: falha de transcrição nunca vira resposta "como se o áudio tivesse sido ouvido"; retomada sem despacho
duplicado; intervenção humana durante a decodificação é respeitada. Handler real `whatsapp.transcribe_audio`; só o provedor
de STT/WhatsApp e o despacho são substituídos (e contados)."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

import jobs.handlers as handlers
from models.contact import Contact
from models.message import Message, MessageDirection, MessageMediaType
from providers.stt.base import STTProviderError


@pytest.fixture
async def world(db_engine, monkeypatch):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    dispatched, transcribed = [], []

    class W:
        pass
    w = W()
    w.sessions, w.dispatched, w.transcribed, w.transcript = sessions, dispatched, transcribed, "quero duas latas de tinta branca"

    async def fake_transcribe(db, provider, inbound):
        transcribed.append(1)
        return w.transcript

    async def fake_dispatch(db, provider, inbound, contact, message, media_type):
        dispatched.append((inbound.text, media_type, message.id))
    monkeypatch.setattr("webhooks.router._transcribe_audio", fake_transcribe)
    monkeypatch.setattr("webhooks.router.dispatch_inbound", fake_dispatch)
    monkeypatch.setattr(handlers, "get_whatsapp_provider", lambda: object())
    return w


async def _audio_message(w, *, content="", media=MessageMediaType.AUDIO):
    async with w.sessions() as db:
        c = Contact(name="C", phone="5511999994001", preferences={})
        db.add(c)
        await db.flush()
        m = Message(contact_id=c.id, direction=MessageDirection.INBOUND, media_type=media, content=content, whatsapp_instance="MARQUESCOLOR",
                    external_id="EXT-1")
        db.add(m)
        await db.commit()
        return c.id, m.id


async def _run(w, message_id):
    async with w.sessions() as db:
        await handlers.transcribe_whatsapp_audio(db, {"message_id": message_id})


async def test_transcricao_vazia_levanta_erro_e_nao_despacha_nada(world):
    world.transcript = "   "
    cid, mid = await _audio_message(world)
    with pytest.raises(STTProviderError):
        await _run(world, mid)                                   # a fila reexecuta; nenhuma fala é inventada
    assert world.dispatched == []
    async with world.sessions() as db:
        assert (await db.get(Message, mid)).content == ""        # nada foi gravado como se fosse a fala do cliente


async def test_transcricao_boa_e_despachada_uma_vez_com_o_texto_real(world):
    cid, mid = await _audio_message(world)
    await _run(world, mid)
    assert world.dispatched == [("quero duas latas de tinta branca", "audio", mid)]
    async with world.sessions() as db:
        assert (await db.get(Message, mid)).content == "quero duas latas de tinta branca"


async def test_transcricao_ja_persistida_nao_chama_o_stt_de_novo(world):
    cid, mid = await _audio_message(world, content="texto já transcrito")
    await _run(world, mid)
    assert world.transcribed == [] and world.dispatched[0][0] == "texto já transcrito"


async def test_resposta_ja_enfileirada_nao_e_despachada_de_novo(world, monkeypatch):
    cid, mid = await _audio_message(world)
    from repositories.job import JobRepository

    async def already(self, message_id):
        return True
    monkeypatch.setattr(JobRepository, "has_inbound_reply", already)
    await _run(world, mid)
    assert world.dispatched == [] and world.transcribed == []


async def test_humano_respondeu_durante_a_decodificacao_nao_rearma_o_agente(world):
    cid, mid = await _audio_message(world)
    async with world.sessions() as db:
        db.add(Message(contact_id=cid, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType.TEXT, content="oi, é a equipe",
                       sent_by_human=True, whatsapp_instance="MARQUESCOLOR"))
        await db.commit()
    await _run(world, mid)
    assert world.dispatched == []                                 # a intervenção humana é preservada
    async with world.sessions() as db:
        assert (await db.get(Message, mid)).content == "quero duas latas de tinta branca"   # a transcrição fica registrada para o humano


@pytest.mark.parametrize("media", [MessageMediaType.TEXT, MessageMediaType.IMAGE])
async def test_mensagem_que_nao_e_audio_e_ignorada(world, media):
    cid, mid = await _audio_message(world, content="legenda", media=media)
    await _run(world, mid)
    assert world.dispatched == [] and world.transcribed == []


async def test_mensagem_inexistente_ou_saida_e_ignorada(world):
    await _run(world, 99999)
    cid, mid = await _audio_message(world)
    async with world.sessions() as db:
        m = await db.get(Message, mid)
        m.direction = MessageDirection.OUTBOUND
        await db.commit()
    await _run(world, mid)
    assert world.dispatched == []
