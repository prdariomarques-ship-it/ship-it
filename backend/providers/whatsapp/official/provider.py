"""Official WhatsApp Cloud API provider (Meta Graph API).

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
"""
import hashlib
import hmac
from collections.abc import Mapping

from providers.whatsapp.base import InboundMessage, WhatsAppProvider, normalize_phone
from utils.config import get_settings

_KNOWN_MEDIA = {"text", "image", "document", "audio", "location"}
_MEDIA_ALIASES = {"document": "pdf"}


class OfficialProvider(WhatsAppProvider):
    name = "official"

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.official_api_base_url.rstrip("/")
        self._token = settings.official_access_token
        self._phone_number_id = settings.official_phone_number_id
        self._app_secret = settings.official_app_secret

    def verify_signature(self, raw_body: bytes, headers: Mapping[str, str]) -> bool:
        """Meta signs every webhook delivery with X-Hub-Signature-256 (HMAC-SHA256
        over the raw body, keyed with the app secret). Skipped if OFFICIAL_APP_SECRET
        isn't configured, to avoid breaking existing setups that rely solely on
        WEBHOOK_SECRET — configure it for real production hardening."""
        if not self._app_secret:
            return True
        signature = headers.get("x-hub-signature-256", "")
        if not signature.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(self._app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    async def _send(self, body: dict) -> dict:
        url = f"{self._base_url}/{self._phone_number_id}/messages"
        return await self._request(
            "POST",
            url,
            json_body={"messaging_product": "whatsapp", "recipient_type": "individual", **body},
            headers=self._headers(),
        )

    async def send_text(self, to: str, content: str) -> dict:
        return await self._send(
            {"to": normalize_phone(to), "type": "text", "text": {"body": content}}
        )

    async def send_image(self, to: str, url: str, filename: str = "image", caption: str = "") -> dict:
        return await self._send(
            {"to": normalize_phone(to), "type": "image", "image": {"link": url, "caption": caption}}
        )

    async def send_file(self, to: str, url: str, filename: str = "file", caption: str = "") -> dict:
        return await self._send(
            {
                "to": normalize_phone(to),
                "type": "document",
                "document": {"link": url, "filename": filename, "caption": caption},
            }
        )

    async def send_audio(self, to: str, url: str) -> dict:
        return await self._send(
            {"to": normalize_phone(to), "type": "audio", "audio": {"link": url}}
        )

    async def send_location(self, to: str, latitude: float, longitude: float, caption: str = "") -> dict:
        return await self._send(
            {
                "to": normalize_phone(to),
                "type": "location",
                "location": {"latitude": latitude, "longitude": longitude, "name": caption},
            }
        )

    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        # Cloud API: entry[].changes[].value.{messages[], contacts[]}
        try:
            value = payload["entry"][0]["changes"][0]["value"]
            message = value["messages"][0]
        except (KeyError, IndexError, TypeError):
            return None

        media_type = message.get("type", "text")
        text = ""
        if media_type == "text":
            text = message.get("text", {}).get("body", "")
        elif media_type in ("image", "document", "audio"):
            text = message.get(media_type, {}).get("caption", "")
        elif media_type == "location":
            location = message.get("location", {})
            text = f"{location.get('latitude', '')},{location.get('longitude', '')}"

        contacts = value.get("contacts", [{}])
        sender_name = contacts[0].get("profile", {}).get("name", "") if contacts else ""

        if media_type not in _KNOWN_MEDIA:
            media_type = "text"
        return InboundMessage(
            phone=normalize_phone(str(message.get("from", ""))),
            text=text,
            sender_name=sender_name,
            external_id=str(message.get("id", "")),
            media_type=_MEDIA_ALIASES.get(media_type, media_type),
        )
