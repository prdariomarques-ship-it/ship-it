"""Provider layer: factories and webhook normalization across vendors."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.llm.anthropic.provider import AnthropicProvider
from providers.llm.base import (
    STUB_REPLY,
    ChatMessage,
    EmbeddingsNotSupportedError,
    TokenUsage,
    ToolCallRequest,
    ToolSpec,
    estimate_cost_usd,
)
from providers.llm.factory import _build, get_llm_provider
from providers.llm.gemini.provider import GeminiProvider
from providers.llm.glm.provider import GLMProvider
from providers.llm.ollama.provider import OllamaProvider
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


@pytest.mark.asyncio
async def test_openai_chat_reports_token_usage():
    provider = OpenAIProvider(api_key="test-key")
    fake_message = MagicMock(content="oi", tool_calls=None)
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=fake_message)]
    fake_response.usage = MagicMock(prompt_tokens=42, completion_tokens=8)

    with patch.object(provider.client.chat.completions, "create", new=AsyncMock(return_value=fake_response)):
        result = await provider.chat([ChatMessage(role="user", content="oi")])
    assert result.usage.prompt_tokens == 42
    assert result.usage.completion_tokens == 8


@pytest.mark.asyncio
async def test_openai_chat_without_usage_reports_zero():
    provider = OpenAIProvider(api_key="test-key")
    fake_message = MagicMock(content="oi", tool_calls=None)
    fake_response = MagicMock(usage=None)
    fake_response.choices = [MagicMock(message=fake_message)]

    with patch.object(provider.client.chat.completions, "create", new=AsyncMock(return_value=fake_response)):
        result = await provider.chat([ChatMessage(role="user", content="oi")])
    assert result.usage.prompt_tokens == 0
    assert result.usage.completion_tokens == 0


@pytest.mark.asyncio
async def test_anthropic_chat_reports_token_usage():
    provider = AnthropicProvider(api_key="test-key")
    fake_block = MagicMock(type="text", text="oi")
    fake_response = MagicMock()
    fake_response.content = [fake_block]
    fake_response.usage = MagicMock(input_tokens=15, output_tokens=6)

    with patch.object(provider.client.messages, "create", new=AsyncMock(return_value=fake_response)):
        result = await provider.chat([ChatMessage(role="user", content="oi")])
    assert result.usage.prompt_tokens == 15
    assert result.usage.completion_tokens == 6


# --- Multi-LLM: factory selection -------------------------------------------
def test_llm_factory_resolves_every_registered_provider():
    for name, expected_cls in (
        ("openai", OpenAIProvider),
        ("anthropic", AnthropicProvider),
        ("glm", GLMProvider),
        ("gemini", GeminiProvider),
        ("ollama", OllamaProvider),
    ):
        assert isinstance(_build(name), expected_cls)


def test_llm_factory_rejects_unknown_provider(monkeypatch):
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_provider", "not-a-real-provider")
    get_llm_provider.cache_clear()
    with pytest.raises(Exception):  # UnknownProviderError
        get_llm_provider()
    monkeypatch.setattr(get_settings(), "llm_provider", "openai")
    get_llm_provider.cache_clear()


# --- Ollama: OpenAI-compatible local models ----------------------------------
def test_ollama_is_enabled_without_an_api_key():
    provider = OllamaProvider(base_url="http://localhost:11434/v1")
    assert provider.enabled  # local models need no key, just a reachable base_url


def test_ollama_has_no_base_url_when_unconfigured():
    assert not OllamaProvider(base_url="").enabled


@pytest.mark.asyncio
async def test_ollama_embeddings_are_rejected_for_dimension_safety():
    with pytest.raises(EmbeddingsNotSupportedError):
        await OllamaProvider().embed("texto")


@pytest.mark.asyncio
async def test_ollama_chat_reuses_openai_wire_format():
    provider = OllamaProvider(base_url="http://localhost:11434/v1", model="llama3.1")
    fake_message = MagicMock(content="olá!", tool_calls=None)
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=fake_message)]

    with patch.object(provider.client.chat.completions, "create", new=AsyncMock(return_value=fake_response)):
        result = await provider.chat([ChatMessage(role="user", content="oi")])
    assert result.content == "olá!"


@pytest.mark.asyncio
async def test_ollama_without_configured_base_url_returns_stub():
    provider = OllamaProvider(base_url="")
    result = await provider.chat([ChatMessage(role="user", content="oi")])
    assert result.content == STUB_REPLY


# --- Gemini: REST via httpx, no new SDK dependency ---------------------------
def _mock_httpx_response(json_body: dict) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=json_body)
    return response


def _patch_httpx_post(response: MagicMock):
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return patch("providers.llm.gemini.provider.httpx.AsyncClient", return_value=client)


@pytest.mark.asyncio
async def test_gemini_disabled_without_api_key_returns_stub():
    provider = GeminiProvider(api_key="")
    result = await provider.chat([ChatMessage(role="user", content="oi")])
    assert result.content == STUB_REPLY


@pytest.mark.asyncio
async def test_gemini_chat_plain_text_reply():
    provider = GeminiProvider(api_key="test-key")
    body = {"candidates": [{"content": {"parts": [{"text": "Bom dia!"}]}}]}
    with _patch_httpx_post(_mock_httpx_response(body)):
        result = await provider.chat([ChatMessage(role="user", content="oi")])
    assert result.content == "Bom dia!"
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_gemini_chat_returns_function_call():
    provider = GeminiProvider(api_key="test-key")
    body = {
        "candidates": [
            {
                "content": {
                    "parts": [{"functionCall": {"name": "create_task", "args": {"title": "Comprar pão"}}}]
                }
            }
        ]
    }
    with _patch_httpx_post(_mock_httpx_response(body)):
        result = await provider.chat(
            [ChatMessage(role="user", content="crie uma tarefa")],
            tools=[ToolSpec(name="create_task", description="d", parameters={})],
        )
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "create_task"
    assert result.tool_calls[0].arguments == {"title": "Comprar pão"}


@pytest.mark.asyncio
async def test_gemini_tool_result_round_trips_by_synthesized_id():
    """Gemini has no call id; the provider must track name via its own synthesized id."""
    provider = GeminiProvider(api_key="test-key")
    messages = [
        ChatMessage(role="system", content="prompt"),
        ChatMessage(role="user", content="crie uma tarefa"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCallRequest(id="gemini_call_0", name="create_task", arguments={"title": "x"})],
        ),
        ChatMessage(role="tool", content='{"ok": true}', tool_call_id="gemini_call_0"),
    ]
    system_instruction, contents = provider._to_gemini_contents(messages)
    assert system_instruction == {"parts": [{"text": "prompt"}]}
    tool_result_turn = contents[-1]
    assert tool_result_turn["role"] == "user"
    assert tool_result_turn["parts"][0]["functionResponse"]["name"] == "create_task"


@pytest.mark.asyncio
async def test_gemini_embed_returns_vector():
    provider = GeminiProvider(api_key="test-key")
    body = {"embedding": {"values": [0.1, 0.2, 0.3]}}
    with _patch_httpx_post(_mock_httpx_response(body)):
        vector = await provider.embed("texto")
    assert vector == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_gemini_embed_disabled_returns_zero_vector():
    provider = GeminiProvider(api_key="")
    vector = await provider.embed("texto")
    assert vector == [0.0] * len(vector)
    assert all(value == 0.0 for value in vector)


@pytest.mark.asyncio
async def test_gemini_chat_reports_token_usage():
    provider = GeminiProvider(api_key="test-key")
    body = {
        "candidates": [{"content": {"parts": [{"text": "oi"}]}}],
        "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 4, "totalTokenCount": 16},
    }
    with _patch_httpx_post(_mock_httpx_response(body)):
        result = await provider.chat([ChatMessage(role="user", content="oi")])
    assert result.usage.prompt_tokens == 12
    assert result.usage.completion_tokens == 4
    assert result.usage.total_tokens == 16


# --- Token usage / cost estimate ---------------------------------------------
def test_token_usage_addition_sums_both_fields():
    total = TokenUsage(prompt_tokens=10, completion_tokens=5) + TokenUsage(prompt_tokens=3, completion_tokens=2)
    assert total == TokenUsage(prompt_tokens=13, completion_tokens=7)
    assert total.total_tokens == 20


def test_estimate_cost_usd_uses_the_pricing_table():
    usage = TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert estimate_cost_usd("openai", usage) == pytest.approx(0.15 + 0.60)
    assert estimate_cost_usd("anthropic", usage) == pytest.approx(3.00 + 15.00)


def test_estimate_cost_usd_unknown_provider_is_zero():
    usage = TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert estimate_cost_usd("some-future-vendor", usage) == 0.0


def test_estimate_cost_usd_self_hosted_providers_are_free():
    usage = TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert estimate_cost_usd("ollama", usage) == 0.0
