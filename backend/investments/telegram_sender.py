"""Telegram send, ported from the original FlowCore runtime/telegram.py
(verified against that file — same endpoint, same ok:false contract),
adapted from urllib to httpx.

Token-safety: the bot token sits in the URL path (Telegram's own API
design — https://api.telegram.org/bot<token>/sendMessage — not something
this module can avoid). httpx logs the full request URL at INFO by
default (confirmed against this project's own logging config), and any
exception's default string often embeds the request URL too. Every path
here that could log or raise is required to go through a message that
never contains the token — see _redact_token and the tests in
tests/test_telegram_sender.py that assert this with a fake token.
"""
import html
import logging

import httpx

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramError(RuntimeError):
    pass


class TelegramPermanentError(TelegramError):
    """A 4xx (not 429) response — retrying will not help (bad chat id, bot
    blocked, bot removed from the group, ...)."""


class TelegramRateLimitedError(TelegramError):
    """429 Too Many Requests. retry_after_seconds, when Telegram supplied
    one, is read by the worker's backoff (see investments/worker.py)."""

    def __init__(self, retry_after_seconds: float | None) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Rate limited by Telegram (retry_after={retry_after_seconds}s)"
            if retry_after_seconds is not None
            else "Rate limited by Telegram"
        )


class TelegramUncertainOutcomeError(TelegramError):
    """Network/timeout failure with no response — Telegram may or may not
    have received and sent the message. The caller must not blindly
    resend; this needs a human to check before anything goes out again."""


def escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def _redact_token(bot_token: str, text: str) -> str:
    """Strip a token that leaked into a URL or exception string. Belt and
    braces alongside the logger-silencing below — never rely on just one."""
    return text.replace(bot_token, "***") if bot_token else text


async def send_telegram_message(bot_token: str, chat_id: str, text: str, timeout: float = 10) -> dict:
    """Returns {"message_id": int} on confirmed delivery.

    Raises TelegramPermanentError (do not retry), TelegramRateLimitedError
    (retry after retry_after_seconds), or TelegramUncertainOutcomeError
    (do not auto-retry — outcome unknown) — never the bare TelegramError
    base class, so callers can always branch on what actually happened.
    """
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"

    # httpx's own request/response logging would otherwise put the token
    # (embedded in `url`) into application logs at INFO.
    httpx_logger = logging.getLogger("httpx")
    previous_level = httpx_logger.level
    httpx_logger.setLevel(logging.WARNING)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
            except httpx.HTTPError as exc:
                # httpx exceptions stringify with the request URL attached —
                # never pass str(exc) through; build our own message instead.
                raise TelegramUncertainOutcomeError(
                    f"Telegram request failed before a response was received: {type(exc).__name__}"
                ) from None
    finally:
        httpx_logger.setLevel(previous_level)

    try:
        data = response.json()
    except ValueError:
        raise TelegramUncertainOutcomeError("Telegram returned a non-JSON response") from None

    if data.get("ok"):
        message_id = (data.get("result") or {}).get("message_id")
        return {"message_id": message_id}

    description = str(data.get("description", ""))
    if response.status_code == 429:
        retry_after = (data.get("parameters") or {}).get("retry_after")
        raise TelegramRateLimitedError(float(retry_after) if retry_after is not None else None)
    if 400 <= response.status_code < 500:
        raise TelegramPermanentError(_redact_token(bot_token, description) or f"HTTP {response.status_code}")
    raise TelegramUncertainOutcomeError(
        _redact_token(bot_token, description) or f"HTTP {response.status_code}"
    )
