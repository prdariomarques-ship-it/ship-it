"""Provider layer: factories and webhook normalization across vendors."""
import pytest

from providers.llm.anthropic.provider import AnthropicProvider
from providers.llm.base import STUB_REPLY, ChatMessage, EmbeddingsNotSupportedError
from providers.llm.glm.provider import GLMProvider
from providers.llm.openai.provider import OpenAIProvider
from providers.whatsapp.baileys.provider import BaileysProvider
from providers.whatsapp.evolution.provider import EvolutionProvider
from providers.whatsapp.factory import get_whatsapp_provider
from providers.whatsapp.official.provider import OfficialProvider
from providers.whatsapp.openwa.provider import OpenWAProvider


def test_whatsapp_factory_returns_configured_provider():
    get_whatsapp_provider.cache_clear()
    assert isinstance(get_whatsapp_provider(), OpenWAProvider)  # default from conftest env
    get_whatsapp_provider.cache_clear()


def test_openwa_webhook_normalization():
    inbound = OpenWAProvider().parse_webhook(
        {"from": "5511988887777@c.us", "body": "Olá", "notifyName": "João", "id": "m1", "type": "text"}
    )
    assert inbound is not None
    assert inbound.phone == "5511988887777"
    assert inbound.text == "Olá"
    assert inbound.sender_name == "João"


def test_evolution_webhook_normalization():
    inbound = EvolutionProvider().parse_webhook(
        {
            "event": "messages.upsert",
            "data": {
                "key": {"remoteJid": "5511911112222@s.whatsapp.net", "fromMe": False, "id": "e1"},
                "pushName": "Ana",
                "message": {"conversation": "Oi, tudo bem?"},
            },
        }
    )
    assert inbound is not None
    assert inbound.phone == "5511911112222"
    assert inbound.text == "Oi, tudo bem?"
    assert inbound.media_type == "text"


def test_evolution_webhook_ignores_own_messages():
    inbound = EvolutionProvider().parse_webhook(
        {"data": {"key": {"remoteJid": "551199@s.whatsapp.net", "fromMe": True}, "message": {}}}
    )
    assert inbound is None


def test_official_webhook_normalization():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"profile": {"name": "Maria"}, "wa_id": "5511900001111"}],
                            "messages": [
                                {
                                    "from": "5511900001111",
                                    "id": "wamid.X",
                                    "type": "text",
                                    "text": {"body": "Quero um orçamento"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    inbound = OfficialProvider().parse_webhook(payload)
    assert inbound is not None
    assert inbound.phone == "5511900001111"
    assert inbound.text == "Quero um orçamento"
    assert inbound.sender_name == "Maria"


def test_official_webhook_ignores_status_updates():
    assert OfficialProvider().parse_webhook({"entry": [{"changes": [{"value": {}}]}]}) is None


def test_baileys_webhook_normalization():
    inbound = BaileysProvider().parse_webhook(
        {
            "data": {
                "messages": [
                    {
                        "key": {"remoteJid": "5511922223333@s.whatsapp.net", "fromMe": False, "id": "b1"},
                        "pushName": "Pedro",
                        "message": {"extendedTextMessage": {"text": "Bom dia"}},
                    }
                ]
            }
        }
    )
    assert inbound is not None
    assert inbound.phone == "5511922223333"
    assert inbound.text == "Bom dia"


@pytest.mark.asyncio
async def test_llm_providers_degrade_gracefully_without_keys():
    result = await OpenAIProvider(api_key="").chat([ChatMessage(role="user", content="oi")])
    assert result.content == STUB_REPLY
    result = await AnthropicProvider(api_key="").chat([ChatMessage(role="user", content="oi")])
    assert result.content == STUB_REPLY
    result = await GLMProvider(api_key="").chat([ChatMessage(role="user", content="oi")])
    assert result.content == STUB_REPLY


@pytest.mark.asyncio
async def test_anthropic_has_no_embeddings():
    with pytest.raises(EmbeddingsNotSupportedError):
        await AnthropicProvider(api_key="x").embed("texto")
