"""Telegram sender: escaping and the real API's error-response contract
(ok: false -> TelegramError), ported from FlowCore's runtime/telegram.py."""
import pytest

from investments.telegram_sender import TelegramError, escape_html, send_telegram_message


def test_escape_html_escapes_reserved_chars():
    assert escape_html("<b>x&y</b>") == "&lt;b&gt;x&amp;y&lt;/b&gt;"


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None

    async def post(self, url: str, json: dict) -> _FakeResponse:
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_send_telegram_message_returns_result_on_ok(monkeypatch):
    monkeypatch.setattr(
        "investments.telegram_sender.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient({"ok": True, "result": {"message_id": 1}}),
    )
    result = await send_telegram_message("tok", "chat-1", "oi")
    assert result == {"message_id": 1}


@pytest.mark.asyncio
async def test_send_telegram_message_raises_on_not_ok(monkeypatch):
    monkeypatch.setattr(
        "investments.telegram_sender.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient({"ok": False, "description": "bot was blocked"}),
    )
    with pytest.raises(TelegramError, match="bot was blocked"):
        await send_telegram_message("tok", "chat-1", "oi")
