"""Cliente do serviço de voz: sucesso verificado por SHA-256, falhas tipadas, token, limpeza e configuração ausente."""
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from services import voice_client
from utils.config import get_settings

AUDIO = (Path(__file__).parent / "fixtures" / "voice" / "tone_2s_mono.ogg").read_bytes()
SHA = hashlib.sha256(AUDIO).hexdigest()


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "store_voice_url", "http://voice.test")
    monkeypatch.setattr(s, "store_voice_token", "k" * 40)
    monkeypatch.setattr(s, "store_voice_timeout_seconds", 5.0)


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://voice.test")


def _ok_handler(log, *, sha=SHA, audio=AUDIO):
    def handler(request: httpx.Request) -> httpx.Response:
        log.append((request.method, request.url.path, request.headers.get("authorization")))
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["language"] == "pt" and body["request_id"] == "store-voice-1" and body["text"]
            return httpx.Response(200, json={"audio_id": "A1", "sha256": sha, "duration_seconds": 2.0, "engine": "chatterbox",
                                             "model_revision": "rev1", "reference_sha256": "r" * 64})
        if request.method == "GET":
            return httpx.Response(200, content=audio, headers={"content-type": "audio/ogg"})
        return httpx.Response(204)
    return handler


async def test_sucesso_confere_hash_envia_token_e_apaga_no_servico():
    log = []
    async with _client(_ok_handler(log)) as c:
        result = await voice_client.synthesize("Olá", "store-voice-1", client=c)
    assert result.data == AUDIO and result.sha256 == SHA and result.engine == "chatterbox" and result.model_revision == "rev1"
    assert [(m, p) for m, p, _ in log] == [("POST", "/v1/synthesize"), ("GET", "/v1/audio/A1"), ("DELETE", "/v1/audio/A1")]
    assert all(auth == "Bearer " + "k" * 40 for _, _, auth in log)


async def test_hash_diferente_e_recusado():
    async with _client(_ok_handler([], sha="0" * 64)) as c:
        with pytest.raises(voice_client.VoiceRejected) as e:
            await voice_client.synthesize("Olá", "store-voice-1", client=c)
    assert e.value.code == "hash_mismatch"


@pytest.mark.parametrize("status, code", [(429, "busy"), (503, "engine_not_ready"), (504, "generation_timeout"), (500, "engine_failure")])
async def test_indisponibilidade_do_servico_vira_voice_unavailable(status, code):
    def handler(request):
        return httpx.Response(status, json={"error": {"code": code, "message": "x"}})
    async with _client(handler) as c:
        with pytest.raises(voice_client.VoiceUnavailable) as e:
            await voice_client.synthesize("Olá", "store-voice-1", client=c)
    assert e.value.code == code


@pytest.mark.parametrize("status", [400, 401, 404, 413, 422])
async def test_recusas_do_servico_viram_voice_rejected(status):
    async with _client(lambda r: httpx.Response(status, json={"error": {"code": "x", "message": "y"}})) as c:
        with pytest.raises(voice_client.VoiceRejected):
            await voice_client.synthesize("Olá", "store-voice-1", client=c)


async def test_timeout_e_erro_de_transporte():
    def timeout(request):
        raise httpx.ReadTimeout("lento")

    def refused(request):
        raise httpx.ConnectError("recusado")
    for handler, code in ((timeout, "timeout"), (refused, "transport")):
        async with _client(handler) as c:
            with pytest.raises(voice_client.VoiceUnavailable) as e:
                await voice_client.synthesize("Olá", "store-voice-1", client=c)
        assert e.value.code == code


async def test_metadados_malformados():
    async with _client(lambda r: httpx.Response(200, json={"oops": 1})) as c:
        with pytest.raises(voice_client.VoiceRejected) as e:
            await voice_client.synthesize("Olá", "store-voice-1", client=c)
    assert e.value.code == "bad_metadata"


async def test_falha_ao_baixar_o_audio():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"audio_id": "A1", "sha256": SHA, "duration_seconds": 2.0})
        return httpx.Response(404)
    async with _client(handler) as c:
        with pytest.raises(voice_client.VoiceRejected):
            await voice_client.synthesize("Olá", "store-voice-1", client=c)


async def test_falha_ao_apagar_nao_invalida_o_audio():
    def handler(request):
        if request.method == "DELETE":
            raise httpx.ConnectError("caiu")
        return _ok_handler([])(request)
    async with _client(handler) as c:
        assert (await voice_client.synthesize("Olá", "store-voice-1", client=c)).sha256 == SHA


@pytest.mark.parametrize("url, token", [("", "k" * 40), ("http://voice.test", ""), ("ftp://x", "k" * 40)])
async def test_configuracao_ausente_ou_invalida(url, token, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "store_voice_url", url)
    monkeypatch.setattr(s, "store_voice_token", token)
    with pytest.raises(voice_client.VoiceUnavailable) as e:
        await voice_client.synthesize("Olá", "store-voice-1")
    assert e.value.code == "not_configured"


@pytest.mark.parametrize("rid", ["", "voice-1", "curto", "tem espaço no meio", "x" * 65, "-comeca-com-hifen"])
async def test_request_id_fora_do_contrato_nem_chama_a_rede(rid):
    called = []

    def handler(request):
        called.append(request)
        return httpx.Response(200)
    async with _client(handler) as c:
        with pytest.raises(voice_client.VoiceRejected) as e:
            await voice_client.synthesize("Olá", rid, client=c)
    assert e.value.code == "bad_request_id" and called == []
