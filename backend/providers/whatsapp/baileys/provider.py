"""Baileys provider, targeting a REST gateway in front of the Baileys library
(e.g. github.com/ookamiiixd/baileys-api). Baileys itself is a Node library, so
a thin HTTP wrapper is required; endpoints follow the common gateway layout
`POST /{session}/messages/send` with Baileys' native message payloads.
"""

from providers.whatsapp.base import (
    InboundMessage,
    WhatsAppProvider,
    extract_baileys_content,
    normalize_phone,
)
from utils.config import get_settings


class BaileysProvider(WhatsAppProvider):
    name = "baileys"

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.baileys_base_url.rstrip("/")
        self._api_key = settings.baileys_api_key
        self._session = settings.baileys_session

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    @staticmethod
    def _jid(to: str) -> str:
        return to if "@" in to else f"{normalize_phone(to)}@s.whatsapp.net"

    async def _send(self, to: str, message: dict) -> dict:
        return await self._request(
            "POST",
            f"{self._base_url}/{self._session}/messages/send",
            json_body={"jid": self._jid(to), "type": "number", "message": message},
            headers=self._headers(),
        )

    async def send_text(self, to: str, content: str) -> dict:
        return await self._send(to, {"text": content})

    async def send_image(
        self, to: str, url: str, filename: str = "image", caption: str = ""
    ) -> dict:
        return await self._send(to, {"image": {"url": url}, "caption": caption})

    async def send_file(
        self, to: str, url: str, filename: str = "file", caption: str = ""
    ) -> dict:
        return await self._send(
            to, {"document": {"url": url}, "fileName": filename, "caption": caption}
        )

    async def send_audio(self, to: str, url: str) -> dict:
        return await self._send(to, {"audio": {"url": url}})

    async def send_location(
        self, to: str, latitude: float, longitude: float, caption: str = ""
    ) -> dict:
        return await self._send(
            to,
            {"location": {"degreesLatitude": latitude, "degreesLongitude": longitude}},
        )

    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        # Baileys "messages.upsert": {key: {remoteJid, fromMe, id}, pushName, message}
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            return None  # malformed payload (e.g. "data": null) — not a crash
        if isinstance(data.get("messages"), list) and data["messages"]:
            data = data["messages"][0]
        if not isinstance(data, dict):
            return None
        key = data.get("key") or {}
        remote_jid = key.get("remoteJid")
        if not remote_jid or key.get("fromMe"):
            return None

        media_type, text = extract_baileys_content(data.get("message", {}) or {})

        return InboundMessage(
            phone=normalize_phone(str(remote_jid)),
            text=text,
            sender_name=str(data.get("pushName", "")),
            external_id=str(key.get("id", "")),
            media_type=media_type,
        )
