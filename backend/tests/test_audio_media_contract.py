"""Áudio recebido: a chave de mídia COMPLETA percorre a cadeia real, sem substituir os elos.

webhook cru -> `EvolutionProvider.parse_webhook` (real) -> `InboundMessage.media_key` (dicionário completo) -> JSON do job ->
handler real `whatsapp.transcribe_audio` / `whatsapp.transcribe_owner_audio` -> `webhooks.router._transcribe_audio` (real) ->
`EvolutionProvider.download_media` (real; só o transporte HTTP `_request` é substituído) -> STT (duplo que registra o que recebeu).

Complementa test_audio_transcription_guard.py, que troca `_transcribe_audio` inteiro e por isso não prova este contrato."""
import base64
import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

import jobs.handlers as handlers
from models.contact import Contact
from models.message import Message, MessageDirection, MessageMediaType
from providers.stt.base import STTProviderError
from providers.whatsapp.base import InboundMessage, WhatsAppProvider, WhatsAppProviderError
from providers.whatsapp.baileys.provider import BaileysProvider
from providers.whatsapp.evolution.provider import EvolutionProvider
from providers.whatsapp.official.provider import OfficialProvider
from providers.whatsapp.openwa.provider import OpenWAProvider
from utils.config import get_settings
from webhooks.router import _transcribe_audio

JID = "5511999994002@s.whatsapp.net"
KEY = {"remoteJid": JID, "fromMe": False, "id": "AUD-1"}
OWNER_KEY = {"remoteJid": JID, "fromMe": True, "id": "AUD-OWN-1"}
AUDIO = b"OggS\x00fake-opus-bytes"
B64 = base64.b64encode(AUDIO).decode()


def _payload(key=KEY, message=None, instance="darioos"):
    return {"event": "messages.upsert", "instance": instance,
            "data": {"key": dict(key), "pushName": "Cli", "message": message or {"audioMessage": {"mimetype": "audio/ogg; codecs=opus"}}}}


class Transport:
    """Substitui SÓ o transporte HTTP do provedor: registra método/URL/corpo e devolve a resposta (ou levanta o erro) combinada."""

    def __init__(self, response=None):
        self.response, self.calls = response, []

    async def __call__(self, method, url, json_body=None, headers=None, **kwargs):
        self.calls.append((method, url, json_body))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class STT:
    enabled = True

    def __init__(self, text="quero duas latas de tinta branca"):
        self.text, self.calls = text, []

    async def transcribe(self, audio_bytes, mime_type):
        self.calls.append((audio_bytes, mime_type))
        return self.text


@pytest.fixture
def provider(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "evolution_instance", "darioos")
    monkeypatch.setattr(settings, "evolution_personal_instance", "")
    p = EvolutionProvider()
    p.transport = Transport({"base64": B64, "mimetype": "audio/ogg"})
    monkeypatch.setattr(p, "_request", p.transport)
    return p


@pytest.fixture
def stt(monkeypatch):
    s = STT()
    monkeypatch.setattr("webhooks.router.get_stt_provider", lambda: s)
    return s


# ---------------------------------------------------------------- parser

def test_parser_preserva_a_chave_completa_do_audio(provider):
    inbound = provider.parse_webhook(_payload())
    assert inbound.media_type == "audio" and inbound.media_key == KEY
    assert inbound.media_key is not _payload()["data"]["key"]                    # cópia: não compartilha o dicionário do webhook


def test_parser_preserva_from_me_e_remote_jid_no_audio_do_dono(provider):
    inbound = provider.parse_webhook(_payload(OWNER_KEY))
    assert inbound.from_me is True and inbound.media_key == OWNER_KEY


def test_parser_nao_inventa_chave_para_texto(provider):
    inbound = provider.parse_webhook(_payload(message={"conversation": "oi"}))
    assert inbound.media_type == "text" and inbound.media_key is None


def test_parser_guarda_a_chave_tambem_de_outras_midias(provider):
    inbound = provider.parse_webhook(_payload(message={"imageMessage": {"caption": "foto"}}))
    assert inbound.media_type == "image" and inbound.media_key == KEY


# ---------------------------------------------------------------- download real do provedor

async def test_download_usa_o_endpoint_e_a_chave_completa(provider):
    out = await provider.download_media(KEY, instance=None)
    assert out == (AUDIO, "audio/ogg")
    (method, url, body), = provider.transport.calls
    assert method == "POST" and url.endswith("/chat/getBase64FromMediaMessage/darioos")
    assert body == {"message": {"key": KEY}, "convertToMp4": False}               # remoteJid + fromMe + id, não só o id


async def test_download_aceita_prefixo_data_e_mimetype_alternativo(provider):
    provider.transport.response = {"base64": f"data:audio/ogg;base64,{B64}", "mimeType": "audio/mpeg"}
    assert await provider.download_media(KEY) == (AUDIO, "audio/mpeg")


@pytest.mark.parametrize("response", [
    {}, {"base64": ""}, {"base64": None}, {"base64": 123}, {"base64": "isso nao e base64!!"}, {"base64": "data:audio/ogg;base64,@@@"},
    WhatsAppProviderError("gateway fora"),
])
async def test_download_com_falha_vazio_ou_base64_invalido_devolve_none(provider, response):
    provider.transport.response = response
    assert await provider.download_media(KEY) is None
    assert len(provider.transport.calls) == 1                                       # uma tentativa; nada é repetido às cegas


async def test_download_so_enderecaa_as_instancias_configuradas(provider, monkeypatch):
    assert await provider.download_media(KEY, instance="outra-instancia") is None
    assert provider.transport.calls == []                                            # recusado ANTES de qualquer chamada
    assert await provider.download_media(KEY, instance="darioos") == (AUDIO, "audio/ogg")
    assert provider.transport.calls[0][1].endswith("/getBase64FromMediaMessage/darioos")
    assert await provider.download_media(KEY, instance="pessoal") is None            # pessoal só vale se configurada
    monkeypatch.setattr(provider, "_personal_instance", "pessoal")
    assert await provider.download_media(KEY, instance="pessoal") == (AUDIO, "audio/ogg")
    assert provider.transport.calls[-1][1].endswith("/getBase64FromMediaMessage/pessoal")


@pytest.mark.parametrize("cls", [BaileysProvider, OfficialProvider, OpenWAProvider])
async def test_provedor_sem_suporte_nao_sobrescreve_e_devolve_none(cls):
    assert cls.download_media is WhatsAppProvider.download_media
    assert await WhatsAppProvider.download_media(object(), KEY) is None


# ---------------------------------------------------------------- cadeia: webhook -> _transcribe_audio -> STT

async def test_cadeia_webhook_download_stt_entrega_bytes_e_mime_ao_stt(provider, stt):
    inbound = provider.parse_webhook(_payload())
    assert await _transcribe_audio(None, provider, inbound) == "quero duas latas de tinta branca"
    assert stt.calls == [(AUDIO, "audio/ogg")]
    assert provider.transport.calls[0][2]["message"]["key"] == KEY


async def test_sem_chave_ou_stt_desligado_nao_baixa_nada(provider, monkeypatch, stt):
    sem_chave = InboundMessage(phone="5511999994002", text="", external_id="X", media_type="audio")
    assert await _transcribe_audio(None, provider, sem_chave) == ""
    monkeypatch.setattr("webhooks.router.get_stt_provider", lambda: None)
    assert await _transcribe_audio(None, provider, provider.parse_webhook(_payload())) == ""
    assert provider.transport.calls == [] and stt.calls == []


async def test_download_vazio_nao_chama_o_stt(provider, stt):
    provider.transport.response = {"base64": ""}
    assert await _transcribe_audio(None, provider, provider.parse_webhook(_payload())) == ""
    assert stt.calls == []


# ---------------------------------------------------------------- cadeia pelos handlers reais (com banco)

@pytest.fixture
async def world(db_engine, provider, stt, monkeypatch):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    dispatched = []

    async def fake_dispatch(db, prov, inbound, contact, message, media_type):
        dispatched.append((inbound.text, media_type, message.id))
    monkeypatch.setattr("webhooks.router.dispatch_inbound", fake_dispatch)           # só o despacho ao agente é substituído
    monkeypatch.setattr(handlers, "get_whatsapp_provider", lambda: provider)

    class W:
        pass
    w = W()
    w.sessions, w.dispatched, w.provider, w.stt = sessions, dispatched, provider, stt
    return w


async def _message(w, *, external_id="AUD-1", content="", direction=MessageDirection.INBOUND, instance="darioos", by_human=False):
    async with w.sessions() as db:
        c = Contact(name="C", phone="5511999994002", preferences={})
        db.add(c)
        await db.flush()
        m = Message(contact_id=c.id, direction=direction, media_type=MessageMediaType.AUDIO, content=content, whatsapp_instance=instance,
                    external_id=external_id, sent_by_human=by_human)
        db.add(m)
        await db.commit()
        return c.id, m.id


def _job_payload(provider, message_id, key=KEY):
    """O payload exatamente como o webhook o grava: a chave sai do parser e passa por JSON (como no banco de jobs)."""
    inbound = provider.parse_webhook(_payload(key))
    return json.loads(json.dumps({"message_id": message_id, "media_key": inbound.media_key}))


async def test_handler_de_audio_recebido_baixa_com_a_chave_completa_e_despacha(world):
    cid, mid = await _message(world)
    async with world.sessions() as db:
        await handlers.transcribe_whatsapp_audio(db, _job_payload(world.provider, mid))
    assert world.provider.transport.calls[0][2]["message"]["key"] == KEY
    assert world.stt.calls == [(AUDIO, "audio/ogg")]
    assert world.dispatched == [("quero duas latas de tinta branca", "audio", mid)]
    async with world.sessions() as db:
        assert (await db.get(Message, mid)).content == "quero duas latas de tinta branca"


@pytest.mark.parametrize("response", [{"base64": ""}, {"base64": "@@@"}, WhatsAppProviderError("fora")])
async def test_handler_com_download_que_falha_levanta_erro_e_nao_despacha(world, response):
    world.provider.transport.response = response
    cid, mid = await _message(world)
    with pytest.raises(STTProviderError):
        async with world.sessions() as db:
            await handlers.transcribe_whatsapp_audio(db, _job_payload(world.provider, mid))
    assert world.dispatched == [] and world.stt.calls == []                           # a fila reexecuta; nada é inventado
    async with world.sessions() as db:
        assert (await db.get(Message, mid)).content == ""


async def test_handler_com_transcricao_ja_gravada_nao_baixa_de_novo(world):                # retomada
    cid, mid = await _message(world, content="texto já transcrito")
    async with world.sessions() as db:
        await handlers.transcribe_whatsapp_audio(db, _job_payload(world.provider, mid))
    assert world.provider.transport.calls == [] and world.stt.calls == []
    assert world.dispatched[0][0] == "texto já transcrito"


async def test_humano_respondeu_durante_o_download_nao_rearma_o_agente(world):               # intervenção humana
    cid, mid = await _message(world)
    async with world.sessions() as db:
        db.add(Message(contact_id=cid, direction=MessageDirection.OUTBOUND, media_type=MessageMediaType.TEXT, content="oi, é a equipe",
                       sent_by_human=True, whatsapp_instance="darioos"))
        await db.commit()
    async with world.sessions() as db:
        await handlers.transcribe_whatsapp_audio(db, _job_payload(world.provider, mid))
    assert world.dispatched == []
    assert world.provider.transport.calls[0][2]["message"]["key"] == KEY                  # baixou e transcreveu, mas não despachou
    async with world.sessions() as db:
        assert (await db.get(Message, mid)).content == "quero duas latas de tinta branca"


async def test_audio_do_dono_passa_a_chave_completa_ao_download(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "evolution_personal_instance", "pessoal")
    monkeypatch.setattr(world.provider, "_personal_instance", "pessoal")
    cid, mid = await _message(world, external_id="AUD-OWN-1", direction=MessageDirection.OUTBOUND, instance="pessoal", by_human=True)
    async with world.sessions() as db:
        await handlers.transcribe_owner_audio(db, _job_payload(world.provider, mid, OWNER_KEY))
    (method, url, body), = world.provider.transport.calls
    assert url.endswith("/getBase64FromMediaMessage/pessoal") and body["message"]["key"] == OWNER_KEY   # fromMe + remoteJid preservados
    assert world.stt.calls == [(AUDIO, "audio/ogg")]
    async with world.sessions() as db:
        assert (await db.get(Message, mid)).content == "quero duas latas de tinta branca"   # só preenche o histórico; nada é despachado
    assert world.dispatched == []


@pytest.mark.parametrize("key", [KEY, {**OWNER_KEY, "id": "OUTRO"}, {"id": "AUD-OWN-1"}, "AUD-OWN-1", None])
async def test_audio_do_dono_com_chave_que_nao_confere_e_recusado_sem_baixar(world, monkeypatch, key):
    monkeypatch.setattr(get_settings(), "evolution_personal_instance", "pessoal")
    monkeypatch.setattr(world.provider, "_personal_instance", "pessoal")
    cid, mid = await _message(world, external_id="AUD-OWN-1", direction=MessageDirection.OUTBOUND, instance="pessoal", by_human=True)
    with pytest.raises(STTProviderError):
        async with world.sessions() as db:
            await handlers.transcribe_owner_audio(db, {"message_id": mid, "media_key": key})
    assert world.provider.transport.calls == [] and world.stt.calls == []


# ---------------------------------------------------------------- lista de instâncias com STT

async def test_audio_de_instancia_fora_da_lista_nao_sai_do_servidor(provider, stt, monkeypatch):
    from webhooks.router import _transcribe_audio

    monkeypatch.setattr(get_settings(), "stt_instances", "MARQUESCOLOR,b2b-sales")
    inbound = provider.parse_webhook(_payload())
    inbound.instance = "darioos"                   # instância válida para download, mas fora da lista
    assert await _transcribe_audio(None, provider, inbound) == ""
    assert not getattr(stt, "calls", [])           # nem baixou nem transcreveu
    assert provider.transport.calls == []


async def test_audio_de_instancia_na_lista_e_transcrito(provider, stt, monkeypatch):
    from webhooks.router import _transcribe_audio

    monkeypatch.setattr(get_settings(), "stt_instances", "MARQUESCOLOR, darioos")
    inbound = provider.parse_webhook(_payload())
    inbound.instance = "darioos"
    assert await _transcribe_audio(None, provider, inbound) == "quero duas latas de tinta branca"
    assert len(stt.calls) == 1
