"""Telegram send, ported from the original FlowCore runtime/telegram.py
(verified against that file — same endpoint, same error semantics), adapted
from urllib to httpx to match this package's async style.

Outbound only — no webhook, no long-polling. Each of the three feeds keeps
its own bot token + chat id, matching how the user's existing bots are
actually configured (separate identities, not one consolidated destination).
"""
import html

import httpx

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramError(RuntimeError):
    pass


class TelegramNotConfiguredError(TelegramError):
    pass


def escape_html(text: str) -> str:
    return html.escape(text, quote=False)


async def send_telegram_message(bot_token: str, chat_id: str, text: str, timeout: float = 10) -> dict:
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
            data = response.json()
    except httpx.HTTPError as exc:
        raise TelegramError(f"Telegram unreachable: {exc}") from exc

    if not data.get("ok"):
        raise TelegramError(f"Telegram API error: {data}")
    return data["result"]
