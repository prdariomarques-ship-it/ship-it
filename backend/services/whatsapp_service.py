"""Client for the OpenWA (wa-automate) REST API.

Every method maps to an OpenWA easy-api endpoint. All sends are best-effort:
failures are logged and re-raised as WhatsAppError so callers can decide.
"""
import httpx

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class WhatsAppError(RuntimeError):
    pass


class WhatsAppService:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def _post(self, endpoint: str, payload: dict) -> dict:
        url = f"{self._settings.openwa_base_url}/{endpoint}"
        headers = {}
        if self._settings.openwa_api_key:
            headers["api_key"] = self._settings.openwa_api_key
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, json={"args": payload}, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.error("OpenWA call %s failed: %s", endpoint, exc)
            raise WhatsAppError(f"OpenWA call {endpoint} failed") from exc

    async def send_text(self, to: str, content: str) -> dict:
        return await self._post("sendText", {"to": to, "content": content})

    async def send_image(self, to: str, url: str, filename: str, caption: str = "") -> dict:
        return await self._post(
            "sendImage", {"to": to, "file": url, "filename": filename, "caption": caption}
        )

    async def send_file(self, to: str, url: str, filename: str, caption: str = "") -> dict:
        return await self._post(
            "sendFile", {"to": to, "file": url, "filename": filename, "caption": caption}
        )

    async def send_audio(self, to: str, url: str) -> dict:
        return await self._post("sendAudio", {"to": to, "file": url})

    async def send_location(self, to: str, latitude: float, longitude: float, caption: str = "") -> dict:
        return await self._post(
            "sendLocation", {"to": to, "lat": str(latitude), "lng": str(longitude), "loc": caption}
        )


whatsapp_service = WhatsAppService()
