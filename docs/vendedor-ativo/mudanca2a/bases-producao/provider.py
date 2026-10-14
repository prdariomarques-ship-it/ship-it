"""Evolution API provider — https://doc.evolution-api.com."""

import base64
from datetime import datetime, timezone
from urllib.parse import quote

from providers.whatsapp.base import (
    ConnectionEvent,
    ConnectionStatus,
    InboundMessage,
    WhatsAppProvider,
    WhatsAppProviderError,
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
        self._instance_path = quote(self._instance, safe="")
        # Optional second instance (e.g. the owner's personal WhatsApp)
        # sharing this backend. Empty when unconfigured -- see
        # utils/config.py::evolution_personal_instance.
        self._personal_instance = settings.evolution_personal_instance

    def _headers(self) -> dict:
        return {"apikey": self._api_key} if self._api_key else {}

    async def _post(self, path: str, body: dict, *, instance: str | None = None) -> dict:
        if instance and self._resolve_instance({"instance": instance}) is None:
            raise WhatsAppProviderError("Instância de saída não autorizada")
        instance_path = quote(instance, safe="") if instance else self._instance_path
        return await self._request(
            "POST",
            f"{self._base_url}/{path}/{instance_path}",
            json_body=body,
            headers=self._headers(),
        )

    async def send_text(
        self, to: str, content: str, *, instance: str | None = None
    ) -> dict:
        """`instance` overrides the configured default for this one call --
        lets a single provider instance reply through whichever Evolution
        instance a given conversation actually arrived on (see
        evolution_personal_instance). Omitted, this is unchanged from
        before dual-instance routing existed."""
        return await self._post(
            "message/sendText",
            {"number": normalize_phone(to), "text": content},
            instance=instance,
        )

    async def send_text_once(self, to: str, content: str) -> dict:
        """Single attempt for proactive follow-ups whose outcome may be uncertain."""
        return await self._request(
            "POST", f"{self._base_url}/message/sendText/{self._instance_path}",
            json_body={"number": normalize_phone(to), "text": content},
            headers=self._headers(), max_attempts=1,
        )

    async def _send_media(
        self, to: str, url: str, mediatype: str, filename: str, caption: str
    ) -> dict:
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

    async def send_image(
        self, to: str, url: str, filename: str = "image", caption: str = ""
    ) -> dict:
        return await self._send_media(to, url, "image", filename, caption)

    async def send_file(
        self, to: str, url: str, filename: str = "file", caption: str = ""
    ) -> dict:
        return await self._send_media(to, url, "document", filename, caption)

    async def send_audio(self, to: str, url: str) -> dict:
        return await self._post(
            "message/sendWhatsAppAudio", {"number": normalize_phone(to), "audio": url}
        )

    async def send_location(
        self, to: str, latitude: float, longitude: float, caption: str = ""
    ) -> dict:
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
        if not isinstance(payload, dict):
            return None
        matched_instance = self._resolve_instance(payload)
        if matched_instance is None:
            return None
        event = str(payload.get("event", "messages.upsert")).lower().replace("_", ".")
        if event != "messages.upsert":
            return None
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            return None  # malformed payload (e.g. "data": null) — not a crash
        key = data.get("key") or {}
        if not isinstance(key, dict):
            return None
        remote_jid = key.get("remoteJid")
        if not isinstance(remote_jid, str):
            return None
        # fromMe: the owner typed this on the phone (remoteJid is then the
        # *recipient*). Reported to the webhook with from_me=True instead of
        # being dropped, so the twin knows the conversation was answered.
        # The other providers (baileys/openwa/official) still discard fromMe:
        # known gap, intentionally not implemented here.
        from_me = bool(key.get("fromMe"))
        # LID is not a phone number. Use the phone JID only when supplied;
        # never send a reply to a group, broadcast list or unresolved LID.
        if remote_jid.endswith("@lid"):
            remote_jid = key.get("remoteJidAlt", "")
        if not isinstance(remote_jid, str) or not remote_jid.endswith(
            ("@s.whatsapp.net", "@c.us")
        ):
            return None
        phone = normalize_phone(remote_jid)
        if not phone.isdigit() or not key.get("id"):
            return None
        message = data.get("message")
        if not isinstance(message, dict) or not message:
            return None

        media_type, text = extract_baileys_content(message)
        timestamp = None
        try:
            if data.get("messageTimestamp") is not None:
                timestamp = datetime.fromtimestamp(
                    int(data["messageTimestamp"]), timezone.utc
                )
        except (ValueError, TypeError, OverflowError, OSError):
            pass

        return InboundMessage(
            phone=phone,
            text=text,
            # On fromMe events pushName is the owner's own name, not the
            # contact's: never let it name/rename the contact.
            sender_name="" if from_me else str(data.get("pushName", "")),
            external_id=str(key.get("id", "")),
            media_type=media_type,
            timestamp=timestamp,
            from_me=from_me,
            instance=matched_instance,
            media_key=key,
        )

    async def download_media(
        self, media_key: dict, *, instance: str | None = None
    ) -> tuple[bytes, str] | None:
        """Evolution decrypts and returns inbound media as base64 via
        getBase64FromMediaMessage -- avoids re-implementing WhatsApp/Baileys'
        own E2E media decryption (AES-CBC with an HKDF-derived key)
        ourselves. Returns None on any failure; callers must treat that the
        same as "this provider doesn't support media download"."""
        if instance and instance not in {self._instance, self._personal_instance}:
            return None
        try:
            result = await self._post(
                "chat/getBase64FromMediaMessage",
                {"message": {"key": media_key}, "convertToMp4": False},
                instance=instance,
            )
        except WhatsAppProviderError:
            return None
        encoded = result.get("base64")
        mime_type = result.get("mimetype") or result.get("mimeType") or "audio/ogg"
        if not encoded:
            return None
        try:
            if encoded.startswith("data:"):
                encoded = encoded.split(",", 1)[1]
            return base64.b64decode(encoded, validate=True), mime_type
        except (ValueError, TypeError, IndexError):
            return None

    def _resolve_instance(self, payload: dict) -> str | None:
        """Which configured instance this payload belongs to (the default
        evolution_instance, or evolution_personal_instance when that's set),
        or None when it matches neither -- e.g. a webhook redelivered after
        an instance was renamed/removed, or another tenant's Evolution
        server pointed here by mistake. A payload with no "instance" field
        at all is assumed to be the default instance, matching Evolution's
        own behaviour on single-instance deployments."""
        instance = payload.get("instance", self._instance)
        known = {self._instance, "b2b-sales", "azusa-church"}
        if self._personal_instance:
            known.add(self._personal_instance)
        return instance if instance in known else None

    def parse_connection_event(self, payload: dict) -> ConnectionEvent | None:
        if not isinstance(payload, dict) or self._resolve_instance(payload) is None:
            return None
        if (
            str(payload.get("event", "")).lower().replace("_", ".")
            != "connection.update"
        ):
            return None
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        state = data.get("state")
        statuses = {
            "open": ConnectionStatus.CONNECTED,
            "close": ConnectionStatus.DISCONNECTED,
            "connecting": ConnectionStatus.RECONNECTING,
        }
        if not isinstance(state, str):
            return None
        return ConnectionEvent(
            status=statuses.get(state, ConnectionStatus.UNKNOWN), detail=state
        )

    async def instance_state(self, instance: str) -> str:
        if instance not in {self._instance, self._personal_instance}:
            return "unknown"
        if not self._base_url or not self._api_key or not instance:
            return "unknown"
        try:
            data = await self._request(
                "GET",
                f"{self._base_url}/instance/connectionState/{quote(instance, safe='')}",
                headers=self._headers(),
                timeout=5,
                max_attempts=1,
            )
            result = data.get("instance")
            state = result.get("state") if isinstance(result, dict) else None
            return state if state in {"open", "close", "connecting"} else "unknown"
        except (WhatsAppProviderError, ValueError, TypeError):
            return "unknown"

    async def health_check(self) -> bool:
        return await self.instance_state(self._instance) == "open"
