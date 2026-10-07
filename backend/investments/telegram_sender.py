"""Telegram send, ported from the original FlowCore runtime/telegram.py
(verified against that file — same endpoint, same ok:false contract),
adapted from urllib to httpx.

Token-safety: the bot token sits in the URL path (Telegram's own API
design — https://api.telegram.org/bot<token>/sendMessage — not something
this module can avoid). httpx logs the full request URL at INFO by
default (confirmed against this project's own logging config), and any
exception's default string often embeds the request URL too.

Two independent layers, deliberately not relying on just one:
  1. A regex-based logging.Filter, attached once at import time to the
     "httpx" logger, that redacts any token-shaped substring from every
     record it emits. This used to be a temporary mutation of the
     logger's level around each call — removed because logging.Logger is
     process-global shared state: two concurrent sends interleaving their
     own setLevel()/finally-reset could leave the window open for one of
     them. A Filter has no shared mutable state to race on — every call
     gets its own LogRecord — so this is safe under any concurrency,
     including if a future change makes _execute() run jobs concurrently
     (today's worker loop is sequential, but nothing here should depend
     on that staying true).
  2. _redact_token, applied to anything this module raises itself.
Tests in tests/test_telegram_sender.py assert both hold under a fake
token for every outcome, including with real concurrent calls.
"""
import html
import logging
import re

import httpx

TELEGRAM_API_BASE = "https://api.telegram.org"

_TOKEN_SHAPE = re.compile(r"\d{6,}:[A-Za-z0-9_-]{20,}")


class _TokenRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # httpx logs "HTTP Request: %s %s ..." with the URL as an httpx.URL
        # object in record.args, not a str — a plain isinstance(arg, str)
        # check on the raw args misses it entirely (confirmed: that was
        # this filter's first, broken version). getMessage() does the
        # %-formatting itself, stringifying every arg type, so the token
        # shape is always matchable in the result regardless of what type
        # produced it.
        message = record.getMessage()
        if _TOKEN_SHAPE.search(message):
            record.msg = _TOKEN_SHAPE.sub("***:***", message)
            record.args = ()
        return True


logging.getLogger("httpx").addFilter(_TokenRedactionFilter())


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
    braces alongside the logging.Filter above — never rely on just one."""
    return text.replace(bot_token, "***") if bot_token else text


async def send_telegram_message(bot_token: str, chat_id: str, text: str, timeout: float = 10) -> dict:
    """Returns {"message_id": int} on confirmed delivery.

    Raises TelegramPermanentError (do not retry), TelegramRateLimitedError
    (retry after retry_after_seconds), or TelegramUncertainOutcomeError
    (do not auto-retry — outcome unknown) — never the bare TelegramError
    base class, so callers can always branch on what actually happened.
    """
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
        except httpx.HTTPError as exc:
            # httpx exceptions stringify with the request URL attached —
            # never pass str(exc) through; build our own message instead.
            raise TelegramUncertainOutcomeError(
                f"Telegram request failed before a response was received: {type(exc).__name__}"
            ) from None

    try:
        data = response.json()
    except ValueError:
        raise TelegramUncertainOutcomeError("Telegram returned a non-JSON response") from None

    if data.get("ok"):
        message_id = (data.get("result") or {}).get("message_id")
        if not isinstance(message_id, int):
            # ok:true with no usable message_id would never normally
            # happen per Telegram's documented contract, but "the API said
            # ok" is not by itself proof of delivery — only a real
            # message_id is. Treated as uncertain, not confidently
            # delivered, so the caller never marks this SUCCEEDED-as-sent
            # on a response that doesn't actually back that up.
            raise TelegramUncertainOutcomeError(
                "Telegram responded ok:true but with no usable message_id"
            )
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
