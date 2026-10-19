"""Minimal JSON-over-HTTPS fetcher (stdlib). Injected into providers so tests never touch the network."""
from __future__ import annotations

import json
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..domain import ProviderError

JsonFetcher = Callable[[str], object]
USER_AGENT = "market-bots/1.0 (+personal use)"
MAX_BYTES = 2_000_000


def fetch_json(url: str, timeout: float = 8.0) -> object:
    if not url.startswith("https://"):
        raise ProviderError("only https sources are allowed")
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - scheme checked above
            raw = resp.read(MAX_BYTES + 1)
    except HTTPError as exc:
        raise ProviderError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderError("source unreachable") from exc
    if len(raw) > MAX_BYTES:
        raise ProviderError("response too large")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise ProviderError("invalid JSON from source") from exc
