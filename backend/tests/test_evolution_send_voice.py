"""Contrato do envio de voz no provedor Evolution: endpoint, corpo, instância, um único POST em resultado ambíguo."""
import base64
from unittest.mock import patch

import httpx
import pytest

from providers.whatsapp.base import WhatsAppProviderError, provably_not_sent
from providers.whatsapp.evolution.provider import EvolutionProvider
from utils.config import get_settings


class _Client:
    def __init__(self, outcomes):
        self.requests = []
        self._outcomes = list(outcomes)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def request(self, method, url, json=None, headers=None):
        self.requests.append((method, url, json, headers))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _resp(body=None, status=200):
    return httpx.Response(status, json=body or {"key": {"id": "REC-1"}}, request=httpx.Request("POST", "http://x"))


@pytest.fixture
def provider(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "evolution_base_url", "http://evo.test")
    monkeypatch.setattr(s, "evolution_api_key", "chave-de-teste")
    monkeypatch.setattr(s, "evolution_instance", "MARQUESCOLOR")
    monkeypatch.setattr(s, "whatsapp_request_max_attempts", 3)
    monkeypatch.setattr(s, "whatsapp_request_backoff_seconds", 0)
    return EvolutionProvider()


async def test_contrato_do_envio_de_voz(provider):
    b64 = base64.b64encode(b"OggS...").decode()
    client = _Client([_resp()])
    with patch("providers.whatsapp.base.httpx.AsyncClient", return_value=client):
        result = await provider.send_voice("+5511999990000", b64, instance="MARQUESCOLOR")
    assert result["key"]["id"] == "REC-1" and len(client.requests) == 1
    method, url, body, headers = client.requests[0]
    assert (method, url) == ("POST", "http://evo.test/message/sendWhatsAppAudio/MARQUESCOLOR")
    assert body == {"number": "5511999990000", "audio": b64} and headers == {"apikey": "chave-de-teste"}


async def test_sem_instancia_usa_a_instancia_padrao_da_loja(provider):
    client = _Client([_resp()])
    with patch("providers.whatsapp.base.httpx.AsyncClient", return_value=client):
        await provider.send_voice("5511999990000", "QUJD")
    assert client.requests[0][1].endswith("/sendWhatsAppAudio/MARQUESCOLOR")


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("lento"), httpx.RemoteProtocolError("cortou"), httpx.ReadError("x")])
async def test_resultado_ambiguo_gera_um_unico_post(provider, exc):
    client = _Client([exc, _resp()])
    with patch("providers.whatsapp.base.httpx.AsyncClient", return_value=client):
        with pytest.raises(WhatsAppProviderError) as e:
            await provider.send_voice("5511999990000", "QUJD")
    assert len(client.requests) == 1 and not provably_not_sent(e.value)


async def test_http_500_nao_e_repetido(provider):
    client = _Client([_resp({"error": "x"}, status=500), _resp()])
    with patch("providers.whatsapp.base.httpx.AsyncClient", return_value=client):
        with pytest.raises(WhatsAppProviderError) as e:
            await provider.send_voice("5511999990000", "QUJD")
    assert len(client.requests) == 1 and not provably_not_sent(e.value)


async def test_conexao_recusada_e_provadamente_nao_enviada(provider):
    client = _Client([httpx.ConnectError("recusado")] * 3)
    with patch("providers.whatsapp.base.httpx.AsyncClient", return_value=client):
        with pytest.raises(WhatsAppProviderError) as e:
            await provider.send_voice("5511999990000", "QUJD")
    assert provably_not_sent(e.value)


async def test_audio_vazio_e_recusado_antes_de_qualquer_rede(provider):
    client = _Client([_resp()])
    with patch("providers.whatsapp.base.httpx.AsyncClient", return_value=client):
        with pytest.raises(ValueError):
            await provider.send_voice("5511999990000", "")
    assert client.requests == []


async def test_outros_provedores_recusam_voz_sem_enviar():
    from providers.whatsapp.baileys.provider import BaileysProvider
    with pytest.raises(WhatsAppProviderError, match="não suportado"):
        await BaileysProvider().send_voice("5511999990000", "QUJD")
