"""OpenWA (wa-automate) provider — https://docs.openwa.dev.

OpenWA posts every event (messages, session state changes, delivery acks) to
the same configured webhook URL, distinguished by an `event` field. This
provider is the only one that translates the session/ack event shapes today —
see providers/whatsapp/README.md for how to add them to another provider.
"""
from datetime import datetime, timezone

from providers.whatsapp.base import (
    ConnectionEvent,
    ConnectionStatus,
    DeliveryAck,
    DeliveryStatus,
    InboundMessage,
    WhatsAppProvider,
    normalize_phone,
)
from utils.config import get_settings

_KNOWN_MEDIA = {"text", "image", "pdf", "audio", "location"}

# wa-automate's onStateChanged values: https://docs.openwa.dev/enums/state.html
_DISCONNECTED_STATES = {"UNPAIRED", "UNPAIRED_IDLE", "UNLAUNCHED"}
_RECONNECTING_STATES = {"TIMEOUT", "CONFLICT", "OPENING", "PAIRING"}


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

    async def health_check(self) -> bool:
        """Ping OpenWA's own status endpoint (easy-api exposes GET /getConnectionState).

        Single-shot (no retry): a readiness probe is polled frequently and
        must answer fast, even when the gateway is genuinely down.
        """
        try:
            result = await self._request(
                "GET",
                f"{self._base_url}/getConnectionState",
                headers=self._headers(),
                timeout=5,
                max_attempts=1,
            )
        except Exception:  # noqa: BLE001 - unreachable/misconfigured gateway = unhealthy, not a crash
            return False
        state = str(result.get("response", result.get("state", ""))).upper()
        return state == "CONNECTED" or bool(result)

    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        if payload.get("event") not in (None, "onMessage", "onAnyMessage"):
            return None  # a session/ack event, not a message — see the other parse_* methods
        # OpenWA posts either the raw message or {"event": "onMessage", "data": {...}}
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            return None  # malformed payload (e.g. "data": null) — not a crash
        sender = data.get("from")
        if not sender:
            return None
        media_type = data.get("type", "text")

        timestamp = None
        raw_ts = data.get("t") or data.get("timestamp")
        if raw_ts:
            try:
                timestamp = datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                timestamp = None

        return InboundMessage(
            phone=normalize_phone(str(sender)),
            text=str(data.get("body", "") or data.get("caption", "")),
            sender_name=str(data.get("notifyName", "") or data.get("sender", {}).get("pushname", "")),
            external_id=str(data.get("id", "")),
            media_type=media_type if media_type in _KNOWN_MEDIA else "text",
            timestamp=timestamp,
        )

    def parse_connection_event(self, payload: dict) -> ConnectionEvent | None:
        if payload.get("event") != "onStateChanged":
            return None
        data = payload.get("data", "")
        state = str(data.get("state", data) if isinstance(data, dict) else data).upper()

        if state == "CONNECTED":
            status = ConnectionStatus.CONNECTED
        elif state in _DISCONNECTED_STATES:
            status = ConnectionStatus.AUTH_EXPIRED
        elif state in _RECONNECTING_STATES:
            status = ConnectionStatus.RECONNECTING
        elif not state:
            return None
        else:
            status = ConnectionStatus.UNKNOWN
        return ConnectionEvent(status=status, detail=state)

    def parse_delivery_ack(self, payload: dict) -> DeliveryAck | None:
        if payload.get("event") != "onAck":
            return None
        data = payload.get("data", {})
        message_id = data.get("id")
        ack = data.get("ack")
        if message_id is None or ack is None:
            return None

        ack = int(ack)
        if ack <= 0:
            status = DeliveryStatus.FAILED
        elif ack == 1:
            status = DeliveryStatus.SENT
        elif ack == 2:
            status = DeliveryStatus.DELIVERED
        else:
            status = DeliveryStatus.READ
        return DeliveryAck(external_id=str(message_id), status=status)
