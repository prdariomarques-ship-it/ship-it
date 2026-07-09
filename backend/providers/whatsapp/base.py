"""Provider-agnostic WhatsApp contract (Strategy pattern).

Each provider knows how to (a) send every media type through its own API and
(b) normalize its webhook payload into an InboundMessage. The application only
ever sees these neutral types.
"""
from abc import ABC, abstractmethod

import httpx
from pydantic import BaseModel

from utils.logging import get_logger

logger = get_logger(__name__)


class WhatsAppProviderError(RuntimeError):
    pass


class InboundMessage(BaseModel):
    """Webhook payload normalized across providers."""

    phone: str  # digits only, international format
    text: str = ""
    sender_name: str = ""
    external_id: str = ""
    media_type: str = "text"


class WhatsAppProvider(ABC):
    """Strategy interface implemented by every WhatsApp integration."""

    name: str

    @abstractmethod
    async def send_text(self, to: str, content: str) -> dict: ...

    @abstractmethod
    async def send_image(self, to: str, url: str, filename: str = "image", caption: str = "") -> dict: ...

    @abstractmethod
    async def send_file(self, to: str, url: str, filename: str = "file", caption: str = "") -> dict: ...

    @abstractmethod
    async def send_audio(self, to: str, url: str) -> dict: ...

    @abstractmethod
    async def send_location(self, to: str, latitude: float, longitude: float, caption: str = "") -> dict: ...

    @abstractmethod
    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        """Normalize an inbound webhook payload; None for non-message events."""

    async def _request(
        self,
        method: str,
        url: str,
        json_body: dict | None = None,
        headers: dict | None = None,
        timeout: float = 30,
    ) -> dict:
        """Shared HTTP helper with uniform error translation."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, json=json_body, headers=headers)
                response.raise_for_status()
                if response.headers.get("content-type", "").startswith("application/json"):
                    return response.json()
                return {"status": "ok"}
        except httpx.HTTPError as exc:
            logger.error("%s provider call failed (%s %s): %s", self.name, method, url, exc)
            raise WhatsAppProviderError(f"{self.name} request failed: {exc}") from exc


def normalize_phone(raw: str) -> str:
    """Strip provider suffixes/symbols: '5511999@c.us' -> '5511999'."""
    return raw.split("@")[0].split(":")[0].lstrip("+")
