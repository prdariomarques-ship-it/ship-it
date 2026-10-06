"""Telegram sender: escaping, the real API's error contract, and — the
security-critical part — that the bot token never reaches a log line or an
exception message under any outcome (success, 4xx, 429, network failure)."""
import logging

import httpx
import pytest

from investments.telegram_sender import (
    TelegramPermanentError,
    TelegramRateLimitedError,
    TelegramUncertainOutcomeError,
    escape_html,
    send_telegram_message,
)

FAKE_TOKEN = "123456:AAFakeTokenThatMustNeverAppearInAnyLogOrException"

_RealAsyncClient = httpx.AsyncClient  # captured before any monkeypatching


def test_escape_html_escapes_reserved_chars():
    assert escape_html("<b>x&y</b>") == "&lt;b&gt;x&amp;y&lt;/b&gt;"


def _patch_client(monkeypatch, handler) -> None:
    def _make_client(**kwargs):
        kwargs.pop("timeout", None)
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("investments.telegram_sender.httpx.AsyncClient", _make_client)


@pytest.mark.asyncio
async def test_send_telegram_message_returns_message_id_on_ok(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert FAKE_TOKEN in str(request.url)  # sanity: this is really the request we think it is
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    _patch_client(monkeypatch, handler)
    result = await send_telegram_message(FAKE_TOKEN, "chat-1", "oi")
    assert result == {"message_id": 42}


@pytest.mark.asyncio
async def test_send_telegram_message_raises_permanent_on_4xx(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    _patch_client(monkeypatch, handler)
    with pytest.raises(TelegramPermanentError, match="chat not found"):
        await send_telegram_message(FAKE_TOKEN, "chat-1", "oi")


@pytest.mark.asyncio
async def test_send_telegram_message_raises_rate_limited_with_retry_after(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 17}}
        )

    _patch_client(monkeypatch, handler)
    with pytest.raises(TelegramRateLimitedError) as exc_info:
        await send_telegram_message(FAKE_TOKEN, "chat-1", "oi")
    assert exc_info.value.retry_after_seconds == 17.0


@pytest.mark.asyncio
async def test_send_telegram_message_network_failure_is_uncertain_not_permanent(monkeypatch):
    def handler(request: httpx.Request) -> None:
        raise httpx.ConnectTimeout("boom", request=request)

    _patch_client(monkeypatch, handler)
    with pytest.raises(TelegramUncertainOutcomeError):
        await send_telegram_message(FAKE_TOKEN, "chat-1", "oi")


# ── token never leaks ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_never_appears_in_logs_on_success(monkeypatch, caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    _patch_client(monkeypatch, handler)
    with caplog.at_level(logging.DEBUG):
        await send_telegram_message(FAKE_TOKEN, "chat-1", "oi")
    assert FAKE_TOKEN not in caplog.text


@pytest.mark.asyncio
async def test_token_never_appears_in_logs_or_exception_on_network_failure(monkeypatch, caplog):
    def handler(request: httpx.Request) -> None:
        raise httpx.ConnectTimeout(f"Connection failed for url {request.url}", request=request)

    _patch_client(monkeypatch, handler)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(TelegramUncertainOutcomeError) as exc_info:
            await send_telegram_message(FAKE_TOKEN, "chat-1", "oi")
    assert FAKE_TOKEN not in caplog.text
    assert FAKE_TOKEN not in str(exc_info.value)
    assert FAKE_TOKEN not in repr(exc_info.value)


@pytest.mark.asyncio
async def test_token_never_appears_in_exception_on_permanent_error(monkeypatch, caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"ok": False, "description": f"Forbidden for {request.url}"})

    _patch_client(monkeypatch, handler)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(TelegramPermanentError) as exc_info:
            await send_telegram_message(FAKE_TOKEN, "chat-1", "oi")
    assert FAKE_TOKEN not in caplog.text
    assert FAKE_TOKEN not in str(exc_info.value)


@pytest.mark.asyncio
async def test_httpx_logger_level_restored_after_call(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {}})

    _patch_client(monkeypatch, handler)
    httpx_logger = logging.getLogger("httpx")
    original_level = httpx_logger.level
    await send_telegram_message(FAKE_TOKEN, "chat-1", "oi")
    assert httpx_logger.level == original_level
