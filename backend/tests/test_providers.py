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
    assert isinstance(
        get_whatsapp_provider(), OpenWAProvider
    )  # default from conftest env
    get_whatsapp_provider.cache_clear()


def test_openwa_webhook_normalization():
    inbound = OpenWAProvider().parse_webhook(
        {
            "from": "5511988887777@c.us",
            "body": "Olá",
            "notifyName": "João",
            "id": "m1",
            "type": "text",
        }
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
                "key": {
                    "remoteJid": "5511911112222@s.whatsapp.net",
                    "fromMe": False,
                    "id": "e1",
                },
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
        {
            "data": {
                "key": {"remoteJid": "551199@s.whatsapp.net", "fromMe": True},
                "message": {},
            }
        }
    )
    assert inbound is None


def test_official_webhook_normalization():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [
                                {"profile": {"name": "Maria"}, "wa_id": "5511900001111"}
                            ],
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
    assert (
        OfficialProvider().parse_webhook({"entry": [{"changes": [{"value": {}}]}]})
        is None
    )


# --- OpenWA: session state and delivery ack normalization -------------------
@pytest.mark.parametrize(
    "state, expected_status",
    [
        ("CONNECTED", "connected"),
        ("UNPAIRED", "auth_expired"),
        ("UNPAIRED_IDLE", "auth_expired"),
        ("TIMEOUT", "reconnecting"),
        ("CONFLICT", "reconnecting"),
        ("SOME_FUTURE_STATE", "unknown"),
    ],
)
def test_openwa_connection_event_maps_known_states(state, expected_status):
    event = OpenWAProvider().parse_connection_event(
        {"event": "onStateChanged", "data": state}
    )
    assert event is not None
    assert event.status.value == expected_status
    assert event.detail == state


def test_openwa_connection_event_ignores_non_state_events():
    assert (
        OpenWAProvider().parse_connection_event({"event": "onMessage", "data": {}})
        is None
    )


def test_openwa_connection_event_handles_nested_state_shape():
    event = OpenWAProvider().parse_connection_event(
        {"event": "onStateChanged", "data": {"state": "CONNECTED"}}
    )
    assert event is not None
    assert event.status.value == "connected"


@pytest.mark.parametrize(
    "ack, expected_status",
    [
        (0, "failed"),
        (-1, "failed"),
        (1, "sent"),
        (2, "delivered"),
        (3, "read"),
        (4, "read"),
    ],
)
def test_openwa_delivery_ack_maps_ack_levels(ack, expected_status):
    result = OpenWAProvider().parse_delivery_ack(
        {"event": "onAck", "data": {"id": "wamid-1", "ack": ack}}
    )
    assert result is not None
    assert result.external_id == "wamid-1"
    assert result.status.value == expected_status


def test_openwa_delivery_ack_ignores_other_events():
    assert (
        OpenWAProvider().parse_delivery_ack({"event": "onMessage", "data": {}}) is None
    )


def test_openwa_delivery_ack_requires_both_id_and_ack():
    assert (
        OpenWAProvider().parse_delivery_ack(
            {"event": "onAck", "data": {"id": "wamid-1"}}
        )
        is None
    )
    assert (
        OpenWAProvider().parse_delivery_ack({"event": "onAck", "data": {"ack": 1}})
        is None
    )


def test_baileys_webhook_normalization():
    inbound = BaileysProvider().parse_webhook(
        {
            "data": {
                "messages": [
                    {
                        "key": {
                            "remoteJid": "5511922223333@s.whatsapp.net",
                            "fromMe": False,
                            "id": "b1",
                        },
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
    result = await OpenAIProvider(api_key="").chat(
        [ChatMessage(role="user", content="oi")]
    )
    assert result.content == STUB_REPLY
    result = await AnthropicProvider(api_key="").chat(
        [ChatMessage(role="user", content="oi")]
    )
    assert result.content == STUB_REPLY
    result = await GLMProvider(api_key="").chat(
        [ChatMessage(role="user", content="oi")]
    )
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

    with patch.object(
        provider.client.chat.completions,
        "create",
        new=AsyncMock(return_value=fake_response),
    ):
        result = await provider.chat([ChatMessage(role="user", content="oi")])
    assert result.usage.prompt_tokens == 42
    assert result.usage.completion_tokens == 8


@pytest.mark.asyncio
async def test_openai_chat_without_usage_reports_zero():
    provider = OpenAIProvider(api_key="test-key")
    fake_message = MagicMock(content="oi", tool_calls=None)
    fake_response = MagicMock(usage=None)
    fake_response.choices = [MagicMock(message=fake_message)]

    with patch.object(
        provider.client.chat.completions,
        "create",
        new=AsyncMock(return_value=fake_response),
    ):
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

    with patch.object(
        provider.client.messages, "create", new=AsyncMock(return_value=fake_response)
    ):
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

    with patch.object(
        provider.client.chat.completions,
        "create",
        new=AsyncMock(return_value=fake_response),
    ):
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
                    "parts": [
                        {
                            "functionCall": {
                                "name": "create_task",
                                "args": {"title": "Comprar pão"},
                            }
                        }
                    ]
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
            tool_calls=[
                ToolCallRequest(
                    id="gemini_call_0", name="create_task", arguments={"title": "x"}
                )
            ],
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
        "usageMetadata": {
            "promptTokenCount": 12,
            "candidatesTokenCount": 4,
            "totalTokenCount": 16,
        },
    }
    with _patch_httpx_post(_mock_httpx_response(body)):
        result = await provider.chat([ChatMessage(role="user", content="oi")])
    assert result.usage.prompt_tokens == 12
    assert result.usage.completion_tokens == 4
    assert result.usage.total_tokens == 16


# --- Token usage / cost estimate ---------------------------------------------
def test_token_usage_addition_sums_both_fields():
    total = TokenUsage(prompt_tokens=10, completion_tokens=5) + TokenUsage(
        prompt_tokens=3, completion_tokens=2
    )
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


# --- WhatsApp provider transport: retry with exponential backoff ------------
def _json_response(body: dict) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.headers = {"content-type": "application/json"}
    response.json = MagicMock(return_value=body)
    return response


@pytest.mark.asyncio
async def test_whatsapp_request_retries_transient_failures_then_succeeds(monkeypatch):
    """Two transient connection failures followed by a success must still
    return the successful result, having tried exactly three times."""
    import httpx as httpx_module

    from observability.metrics import WHATSAPP_PROVIDER_REQUESTS
    from utils.config import get_settings

    provider = OpenWAProvider()
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_request_max_attempts", 3)
    monkeypatch.setattr(settings, "whatsapp_request_backoff_seconds", 0)

    class _FlakyClient:
        attempts = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def request(self, method, url, json=None, headers=None):
            _FlakyClient.attempts += 1
            if _FlakyClient.attempts < 3:
                raise httpx_module.ConnectError("connection refused")
            return _json_response({"status": "ok"})

    before = WHATSAPP_PROVIDER_REQUESTS.labels(provider.name, "ok")._value.get()
    with patch(
        "providers.whatsapp.base.httpx.AsyncClient", return_value=_FlakyClient()
    ):
        result = await provider._request("GET", "http://example.test/ping")

    assert result == {"status": "ok"}
    assert _FlakyClient.attempts == 3
    assert (
        WHATSAPP_PROVIDER_REQUESTS.labels(provider.name, "ok")._value.get()
        == before + 1
    )


@pytest.mark.asyncio
async def test_whatsapp_request_raises_after_exhausting_all_retries(monkeypatch):
    import httpx as httpx_module

    from observability.metrics import WHATSAPP_PROVIDER_REQUESTS
    from providers.whatsapp.base import WhatsAppProviderError
    from utils.config import get_settings

    provider = OpenWAProvider()
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_request_max_attempts", 2)
    monkeypatch.setattr(settings, "whatsapp_request_backoff_seconds", 0)

    class _AlwaysFailingClient:
        attempts = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def request(self, method, url, json=None, headers=None):
            _AlwaysFailingClient.attempts += 1
            raise httpx_module.ConnectError("gateway is down")

    before = WHATSAPP_PROVIDER_REQUESTS.labels(provider.name, "error")._value.get()
    with patch(
        "providers.whatsapp.base.httpx.AsyncClient", return_value=_AlwaysFailingClient()
    ):
        with pytest.raises(WhatsAppProviderError):
            await provider._request("GET", "http://example.test/ping")

    assert _AlwaysFailingClient.attempts == 2
    assert (
        WHATSAPP_PROVIDER_REQUESTS.labels(provider.name, "error")._value.get()
        == before + 1
    )


@pytest.mark.asyncio
async def test_whatsapp_request_max_attempts_override_skips_retry(monkeypatch):
    """health_check() passes max_attempts=1 so a down gateway fails fast
    instead of blocking a readiness probe through the full backoff."""
    import httpx as httpx_module

    from utils.config import get_settings

    provider = OpenWAProvider()
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_request_max_attempts", 5)
    monkeypatch.setattr(settings, "whatsapp_request_backoff_seconds", 0)

    class _FailingClient:
        attempts = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def request(self, method, url, json=None, headers=None):
            _FailingClient.attempts += 1
            raise httpx_module.ConnectError("down")

    with patch(
        "providers.whatsapp.base.httpx.AsyncClient", return_value=_FailingClient()
    ):
        with pytest.raises(Exception):
            await provider._request("GET", "http://example.test/ping", max_attempts=1)

    assert _FailingClient.attempts == 1
