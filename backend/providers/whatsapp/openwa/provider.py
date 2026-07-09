"""OpenWA (wa-automate) provider — https://docs.openwa.dev."""
from providers.whatsapp.base import InboundMessage, WhatsAppProvider, normalize_phone
from utils.config import get_settings

_KNOWN_MEDIA = {"text", "image", "pdf", "audio", "location"}


class OpenWAProvider(WhatsAppProvider):
    name = "openwa"

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.openwa_base_url.rstrip("/")
        self._api_key = settings.openwa_api_key

    def _headers(self) -> dict:
        return {"api_key": self._api_key} if self._api_key else {}

    async def _post(self, endpoint: str, args: dict) -> dict:
        return await self._request(
            "POST", f"{self._base_url}/{endpoint}", json_body={"args": args}, headers=self._headers()
        )

    @staticmethod
    def _chat_id(to: str) -> str:
        return to if "@" in to else f"{to}@c.us"

    async def send_text(self, to: str, content: str) -> dict:
        return await self._post("sendText", {"to": self._chat_id(to), "content": content})

    async def send_image(self, to: str, url: str, filename: str = "image", caption: str = "") -> dict:
        return await self._post(
            "sendImage",
            {"to": self._chat_id(to), "file": url, "filename": filename, "caption": caption},
        )

    async def send_file(self, to: str, url: str, filename: str = "file", caption: str = "") -> dict:
        return await self._post(
            "sendFile",
            {"to": self._chat_id(to), "file": url, "filename": filename, "caption": caption},
        )

    async def send_audio(self, to: str, url: str) -> dict:
        return await self._post("sendAudio", {"to": self._chat_id(to), "file": url})

    async def send_location(self, to: str, latitude: float, longitude: float, caption: str = "") -> dict:
        return await self._post(
            "sendLocation",
            {"to": self._chat_id(to), "lat": str(latitude), "lng": str(longitude), "loc": caption},
        )

    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        # OpenWA posts either the raw message or {"event": "onMessage", "data": {...}}
        data = payload.get("data", payload)
        sender = data.get("from")
        if not sender:
            return None
        media_type = data.get("type", "text")
        return InboundMessage(
            phone=normalize_phone(str(sender)),
            text=str(data.get("body", "") or data.get("caption", "")),
            sender_name=str(data.get("notifyName", "") or data.get("sender", {}).get("pushname", "")),
            external_id=str(data.get("id", "")),
            media_type=media_type if media_type in _KNOWN_MEDIA else "text",
        )
