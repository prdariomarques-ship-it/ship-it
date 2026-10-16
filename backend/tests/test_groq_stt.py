"""GroqSTTProvider: chamada HTTP simulada (httpx.MockTransport). NÃO prova a qualidade da transcrição nem fala com a Groq de verdade."""
import httpx
import pytest

from providers.stt import groq as groq_module
from providers.stt.base import STTProviderError
from providers.stt.factory import UnknownSTTProviderError, get_stt_provider
from providers.stt.groq import MAX_AUDIO_BYTES, GroqSTTProvider
from utils.config import get_settings

SECRET = "gsk_segredo_de_teste_nao_pode_vazar"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "groq_api_key", SECRET)
    monkeypatch.setattr(settings, "groq_stt_model", "whisper-large-v3-turbo")
    monkeypatch.setattr(settings, "groq_stt_language", "pt")
    monkeypatch.setattr(settings, "stt_provider", "")

    async def no_sleep(_):
        return None
    monkeypatch.setattr(groq_module.asyncio, "sleep", no_sleep)


def _provider(handler):
    return GroqSTTProvider(transport=httpx.MockTransport(handler))


async def test_envia_arquivo_modelo_idioma_e_chave_e_devolve_o_texto():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], request.read()
        return httpx.Response(200, json={"text": "  quero duas latas de tinta branca  "})

    text = await _provider(handler).transcribe(b"OggS-audio", "audio/ogg; codecs=opus")
    assert text == "quero duas latas de tinta branca"
    assert seen["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert seen["auth"] == f"Bearer {SECRET}"
    body = seen["body"]
    assert b'name="model"' in body and b"whisper-large-v3-turbo" in body
    assert b'name="language"' in body and b"\r\n\r\npt\r\n" in body
    assert b'name="temperature"' in body and b'filename="audio.ogg"' in body and b"OggS-audio" in body


async def test_sem_chave_fica_desabilitado_e_nao_chama_a_rede(monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    calls = []
    provider = _provider(lambda request: calls.append(1) or httpx.Response(200, json={"text": "x"}))
    assert provider.enabled is False
    with pytest.raises(STTProviderError):
        await provider.transcribe(b"x", "audio/ogg")
    assert calls == []


@pytest.mark.parametrize("audio,mime", [(b"", "audio/ogg"), (b"x" * (MAX_AUDIO_BYTES + 1), "audio/ogg")])
async def test_audio_vazio_ou_grande_demais_nem_chega_a_rede(audio, mime):
    calls = []
    provider = _provider(lambda request: calls.append(1) or httpx.Response(200, json={"text": "x"}))
    with pytest.raises(STTProviderError):
        await provider.transcribe(audio, mime)
    assert calls == []


async def test_tenta_de_novo_em_429_e_para_em_erro_definitivo():
    answers = iter([httpx.Response(429, json={"error": {"message": "rate limit"}}, headers={"retry-after": "1"}),
                    httpx.Response(200, json={"text": "ok depois da espera"})])
    assert await _provider(lambda request: next(answers)).transcribe(b"x", "audio/ogg") == "ok depois da espera"

    calls = []

    def definitive(request):
        calls.append(1)
        return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})
    with pytest.raises(STTProviderError) as info:
        await _provider(definitive).transcribe(b"x", "audio/ogg")
    assert calls == [1] and "401" in str(info.value) and "Invalid API Key" in str(info.value)


async def test_falha_de_rede_e_5xx_esgotam_as_tentativas_sem_vazar_a_chave():
    def boom(request):
        raise httpx.ConnectTimeout(f"timeout falando com {SECRET}")
    with pytest.raises(STTProviderError) as info:
        await _provider(boom).transcribe(b"x", "audio/ogg")
    assert SECRET not in str(info.value) and "ConnectTimeout" in str(info.value)

    calls = []

    def server_error(request):
        calls.append(1)
        return httpx.Response(503, text="indisponivel")
    with pytest.raises(STTProviderError):
        await _provider(server_error).transcribe(b"x", "audio/ogg")
    assert len(calls) == 2


@pytest.mark.parametrize("payload", [{"text": ""}, {"text": "   "}, {}, {"text": "Legendas pela comunidade Amara.org"}, {"text": "Obrigado por assistir!"}])
async def test_resposta_vazia_ou_alucinacao_do_whisper_nao_vira_texto(payload):
    with pytest.raises(STTProviderError):
        await _provider(lambda request: httpx.Response(200, json=payload)).transcribe(b"x", "audio/ogg")


async def test_obrigado_curto_de_verdade_passa():
    assert await _provider(lambda request: httpx.Response(200, json={"text": "Obrigado!"})).transcribe(b"x", "audio/ogg") == "Obrigado!"


async def test_resposta_que_nao_e_json_e_erro():
    with pytest.raises(STTProviderError):
        await _provider(lambda request: httpx.Response(200, text="<html>")).transcribe(b"x", "audio/ogg")


def test_factory_registra_groq_e_continua_none_por_padrao(monkeypatch):
    settings = get_settings()
    assert get_stt_provider() is None
    monkeypatch.setattr(settings, "stt_provider", "groq")
    assert isinstance(get_stt_provider(), GroqSTTProvider)
    monkeypatch.setattr(settings, "stt_provider", "inexistente")
    with pytest.raises(UnknownSTTProviderError):
        get_stt_provider()
