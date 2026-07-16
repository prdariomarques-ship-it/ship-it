"""Compatibility suite: any class implementing WhatsAppProvider must work
automatically, with zero changes to the application. Two kinds of proof:

1. A parametrized contract test run against every provider registered in the
   factory (openwa, baileys, evolution, official) — same assertions, same
   inputs, no provider-specific special-casing in the test itself.
2. A minimal fake provider, registered only for this test, proving the
   webhook route works through the interface alone — this is the concrete
   demonstration of rule #6: swapping providers is configuration, not code.
"""

from typing import ClassVar

import pytest

from providers.whatsapp import factory as wa_factory
from providers.whatsapp.baileys.provider import BaileysProvider
from providers.whatsapp.base import (
    ConnectionEvent,
    ConnectionStatus,
    DeliveryAck,
    InboundMessage,
    WhatsAppProvider,
)
from providers.whatsapp.evolution.provider import EvolutionProvider
from providers.whatsapp.official.provider import OfficialProvider
from providers.whatsapp.openwa.provider import OpenWAProvider

ALL_PROVIDER_CLASSES = [
    OpenWAProvider,
    BaileysProvider,
    EvolutionProvider,
    OfficialProvider,
]


@pytest.mark.parametrize("provider_cls", ALL_PROVIDER_CLASSES, ids=lambda c: c.name)
class TestEveryProviderSatisfiesTheContract:
    """Same test body for every provider — proves none of them need special
    handling anywhere in the application."""

    def test_is_a_whatsapp_provider(self, provider_cls):
        provider = provider_cls()
        assert isinstance(provider, WhatsAppProvider)
        assert isinstance(provider.name, str) and provider.name

    def test_parse_webhook_never_raises_on_garbage_input(self, provider_cls):
        provider = provider_cls()
        for garbage in (
            {},
            {"garbage": "data"},
            {"event": "something_unexpected"},
            {"data": None},
        ):
            result = provider.parse_webhook(garbage)
            assert result is None or isinstance(result, InboundMessage)

    def test_parse_connection_event_never_raises_on_garbage_input(self, provider_cls):
        provider = provider_cls()
        for garbage in (
            {},
            {"event": "onStateChanged"},
            {"event": "onStateChanged", "data": None},
        ):
            result = provider.parse_connection_event(garbage)
            assert result is None or isinstance(result, ConnectionEvent)

    def test_parse_delivery_ack_never_raises_on_garbage_input(self, provider_cls):
        provider = provider_cls()
        for garbage in ({}, {"event": "onAck"}, {"event": "onAck", "data": {}}):
            result = provider.parse_delivery_ack(garbage)
            assert result is None or isinstance(result, DeliveryAck)

    def test_verify_signature_default_or_configured_behavior_is_a_bool(
        self, provider_cls
    ):
        provider = provider_cls()
        assert isinstance(provider.verify_signature(b"", {}), bool)

    @pytest.mark.asyncio
    async def test_health_check_returns_a_bool_without_raising(self, provider_cls):
        provider = provider_cls()
        # Points at an unreachable default (localhost); must degrade to a
        # clean False/True, never propagate a connection exception.
        assert isinstance(await provider.health_check(), bool)

    def test_declares_all_required_send_methods(self, provider_cls):
        for method_name in (
            "send_text",
            "send_image",
            "send_file",
            "send_audio",
            "send_location",
        ):
            assert callable(getattr(provider_cls, method_name, None)), method_name

    def test_registered_in_the_factory_by_its_own_name(self, provider_cls):
        provider = provider_cls()
        assert wa_factory._PROVIDERS[provider.name] is provider_cls


def test_factory_resolves_every_registered_provider_by_configured_name(monkeypatch):
    from utils.config import get_settings

    for name, expected_cls in wa_factory._PROVIDERS.items():
        monkeypatch.setattr(get_settings(), "whatsapp_provider", name)
        wa_factory.get_whatsapp_provider.cache_clear()
        assert isinstance(wa_factory.get_whatsapp_provider(), expected_cls)
    wa_factory.get_whatsapp_provider.cache_clear()


# --- Rule #6, proven concretely: a brand-new provider needs zero app changes ---
class _FakeProvider(WhatsAppProvider):
    """A minimal, made-up provider — not one of the four shipped ones. If the
    webhook route (or anything else) only depends on the WhatsAppProvider
    interface, this works exactly like OpenWA/Baileys/Evolution/Official
    without a single line of application code changing."""

    name = "fake_test_provider"
    sent: ClassVar[list[tuple[str, str]]] = []

    async def send_text(self, to: str, content: str) -> dict:
        self.sent.append((to, content))
        return {"status": "ok"}

    async def send_image(self, to, url, filename="image", caption="") -> dict:
        return {"status": "ok"}

    async def send_file(self, to, url, filename="file", caption="") -> dict:
        return {"status": "ok"}

    async def send_audio(self, to, url) -> dict:
        return {"status": "ok"}

    async def send_location(self, to, latitude, longitude, caption="") -> dict:
        return {"status": "ok"}

    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        if payload.get("kind") != "chat_message":
            return None
        return InboundMessage(
            phone=str(payload["from_number"]),
            text=str(payload.get("text", "")),
            sender_name=str(payload.get("sender", "")),
            external_id=str(payload.get("id", "")),
        )

    def parse_connection_event(self, payload: dict) -> ConnectionEvent | None:
        if payload.get("kind") != "session_status":
            return None
        return ConnectionEvent(
            status=ConnectionStatus(payload["status"]), detail="fake"
        )


@pytest.fixture
def fake_provider_configured(monkeypatch):
    """Register _FakeProvider in the factory and select it — the only two
    things a new provider ever needs from the application side."""
    monkeypatch.setitem(wa_factory._PROVIDERS, _FakeProvider.name, _FakeProvider)
    from utils.config import get_settings

    monkeypatch.setattr(get_settings(), "whatsapp_provider", _FakeProvider.name)
    wa_factory.get_whatsapp_provider.cache_clear()
    _FakeProvider.sent.clear()
    yield
    wa_factory.get_whatsapp_provider.cache_clear()


@pytest.mark.asyncio
async def test_webhook_route_works_with_a_brand_new_provider_zero_app_changes(
    client, auth_headers, fake_provider_configured
):
    response = await client.post(
        "/api/webhooks/whatsapp",
        json={
            "kind": "chat_message",
            "from_number": "5511900000123",
            "text": "oi",
            "sender": "Fake",
            "id": "fake-1",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "received"

    contacts = await client.get("/api/contacts", headers=auth_headers)
    assert contacts.json()[0]["phone"] == "5511900000123"


@pytest.mark.asyncio
async def test_webhook_route_recognizes_connection_events_from_a_new_provider(
    client, fake_provider_configured
):
    response = await client.post(
        "/api/webhooks/whatsapp", json={"kind": "session_status", "status": "connected"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "session_event"


@pytest.mark.asyncio
async def test_outbound_send_works_through_a_brand_new_provider(
    client, auth_headers, fake_provider_configured
):
    response = await client.post(
        "/api/whatsapp/send-text",
        json={"to": "5511900000999", "content": "olá via fake provider"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert _FakeProvider.sent == [("5511900000999", "olá via fake provider")]
