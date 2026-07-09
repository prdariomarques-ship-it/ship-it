"""Evolution API provider — https://doc.evolution-api.com."""
from providers.whatsapp.base import (
    InboundMessage,
    WhatsAppProvider,
    extract_baileys_content,
    normalize_phone,
)
from utils.config import get_settings


class EvolutionProvider(WhatsAppProvider):
    name = "evolution"

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.evolution_base_url.rstrip("/")
        self._api_key = settings.evolution_api_key
        self._instance = settings.evolution_instance

    def _headers(self) -> dict:
        return {"apikey": self._api_key} if self._api_key else {}

    async def _post(self, path: str, body: dict) -> dict:
        return await self._request(
            "POST", f"{self._base_url}/{path}/{self._instance}", json_body=body, headers=self._headers()
        )

    async def send_text(self, to: str, content: str) -> dict:
        return await self._post("message/sendText", {"number": normalize_phone(to), "text": content})

    async def _send_media(self, to: str, url: str, mediatype: str, filename: str, caption: str) -> dict:
        return await self._post(
            "message/sendMedia",
            {
                "number": normalize_phone(to),
                "mediatype": mediatype,
                "media": url,
                "fileName": filename,
                "caption": caption,
            },
        )

    async def send_image(self, to: str, url: str, filename: str = "image", caption: str = "") -> dict:
        return await self._send_media(to, url, "image", filename, caption)

    async def send_file(self, to: str, url: str, filename: str = "file", caption: str = "") -> dict:
        return await self._send_media(to, url, "document", filename, caption)

    async def send_audio(self, to: str, url: str) -> dict:
        return await self._post(
            "message/sendWhatsAppAudio", {"number": normalize_phone(to), "audio": url}
        )

    async def send_location(self, to: str, latitude: float, longitude: float, caption: str = "") -> dict:
        return await self._post(
            "message/sendLocation",
            {
                "number": normalize_phone(to),
                "latitude": latitude,
                "longitude": longitude,
                "name": caption,
                "address": caption,
            },
        )

    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        # Evolution "messages.upsert" event: {event, instance, data: {key, pushName, message}}
        data = payload.get("data", payload)
        key = data.get("key", {})
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
