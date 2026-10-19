"""Telegram Bot API adapter (stdlib). The token lives only in the URL path of calls made here and is scrubbed from
every error that leaves this module."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

log = logging.getLogger("market_bots.telegram")
API = "https://api.telegram.org"


class DeliveryError(Exception):
    pass


class PollConflict(Exception):
    """Telegram answered 409: another process is long-polling the same token."""


class TransportError(Exception):
    def __init__(self, status: int | None, description: str = "", retry_after: float | None = None) -> None:
        super().__init__(description)
        self.status = status
        self.description = description
        self.retry_after = retry_after


Transport = Callable[[str, dict, float], dict]


def http_transport(url: str, payload: dict, timeout: float) -> dict:
    req = Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https base
            return json.loads(resp.read())
    except HTTPError as exc:
        desc, retry_after = "", None
        try:
            body = json.loads(exc.read())
            desc = str(body.get("description", ""))
            retry_after = (body.get("parameters") or {}).get("retry_after")
        except Exception:  # noqa: BLE001 - the error body is best-effort
            pass
        raise TransportError(exc.code, desc, retry_after) from None
    except (URLError, TimeoutError, OSError):
        raise TransportError(None, "network error") from None
    except ValueError:
        raise TransportError(None, "invalid response") from None


class TelegramApi:
    def __init__(self, token: str, transport: Transport = http_transport, sleep: Callable[[float], None] = time.sleep) -> None:
        self._token = token
        self._transport = transport
        self._sleep = sleep

    def _call(self, method: str, payload: dict, timeout: float) -> dict:
        try:
            body = self._transport(f"{API}/bot{self._token}/{method}", payload, timeout)
        except TransportError as exc:
            if exc.status == 409:
                raise PollConflict("another instance is polling this bot token") from None
            raise DeliveryError(self._scrub(f"{method} failed: HTTP {exc.status} {exc.description}".strip())) from None
        if not body.get("ok"):
            raise DeliveryError(self._scrub(f"{method} rejected: {body.get('description', 'unknown')}"))
        return body

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, "***")

    def send_message(self, chat_id: str, text: str) -> None:
        payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        try:
            self._call("sendMessage", payload, 15.0)
        except DeliveryError as first:
            # One bounded retry for rate limiting / transient 5xx; never loops.
            if "429" in str(first) or "HTTP 5" in str(first):
                self._sleep(2.0)
                self._call("sendMessage", payload, 15.0)
            else:
                raise

    def get_updates(self, offset: int, timeout_s: int = 25) -> list[dict]:
        body = self._call("getUpdates", {"offset": offset, "timeout": timeout_s, "allowed_updates": ["message"]},
                          timeout_s + 10.0)
        result = body.get("result", [])
        return result if isinstance(result, list) else []


class TelegramNotifier:
    def __init__(self, api: TelegramApi) -> None:
        self._api = api

    def send(self, chat_id: str, text: str) -> None:
        self._api.send_message(chat_id, text)


class DryRunNotifier:
    """Default mode: nothing leaves the process. Messages are logged and appended to an outbox file."""

    def __init__(self, outbox: Path | None = None, profile: str = "") -> None:
        self._outbox = outbox
        self._profile = profile
        self.sent: list[tuple[str, str]] = []

    def send(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))
        log.info("[dry-run:%s] would send %d chars to chat %s", self._profile, len(text), chat_id or "(none)")
        if self._outbox:
            with self._outbox.open("a", encoding="utf-8") as fh:
                fh.write(f"--- {self._profile} chat={chat_id or '-'}\n{text}\n")
