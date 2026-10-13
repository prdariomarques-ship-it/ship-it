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
        self.default_instance = self._instance

    def _headers(self) -> dict:
        return {"apikey": self._api_key} if self._api_key else {}

    async def _post(self, path: str, body: dict, instance: str | None = None) -> dict:
        # Review fix: jobs/handlers.py's send_whatsapp_text calls every
        # send_* method below with `instance=` to route a reply back out
        # through a specific Evolution gateway instance (e.g. the owner's
        # personal number vs. the store's) -- this provider accepted no
        # such parameter at all, so every one of those calls would raise
        # TypeError. Falls back to this provider's configured default
        # instance (self._instance) exactly like before when not given.
        return await self._request(
            "POST",
            f"{self._base_url}/{path}/{instance or self._instance}",
            json_body=body,
            headers=self._headers(),
            # Review fix: every call through here is a send -- an ambiguous
            # transport failure (timeout, connection reset, protocol error)
            # doesn't mean the message wasn't delivered. See base.py's
            # _request docstring.
            retry_on_ambiguous_delivery=False,
        )

    async def send_text(self, to: str, content: str, instance: str | None = None) -> dict:
        return await self._post(
            "message/sendText", {"number": normalize_phone(to), "text": content}, instance=instance,
        )

    async def _send_media(
        self, to: str, url: str, mediatype: str, filename: str, caption: str, instance: str | None = None
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
            instance=instance,
        )

    async def send_image(
        self, to: str, url: str, filename: str = "image", caption: str = "", instance: str | None = None
    ) -> dict:
        return await self._send_media(to, url, "image", filename, caption, instance=instance)

    async def send_file(
        self, to: str, url: str, filename: str = "file", caption: str = "", instance: str | None = None
    ) -> dict:
        return await self._send_media(to, url, "document", filename, caption, instance=instance)

    async def send_audio(self, to: str, url: str, instance: str | None = None) -> dict:
        return await self._post(
            "message/sendWhatsAppAudio", {"number": normalize_phone(to), "audio": url}, instance=instance,
        )

    async def send_voice(self, to: str, audio_base64: str, instance: str | None = None) -> dict:
        """Mensagem de VOZ (PTT) a partir de OGG/Opus já validado pelo chamador, enviada como base64.

        Contrato (código-fonte do Evolution API v2, `sendWhatsAppAudio`): POST /message/sendWhatsAppAudio/{instance} com
        {"number", "audio", opcionais "delay" (ms) e "encoding"}. `audio` aceita URL ou base64 **puro** (sem prefixo `data:`; o
        validador do Evolution recusa o prefixo). Com `encoding` ausente/true o servidor converte com ffmpeg para OGG/Opus mono
        48 kHz e envia como nota de voz (ptt) com presença "gravando"; com false envia os bytes como estão. A resposta traz
        `key.id` (recibo). A VERSÃO instalada não foi confirmada aqui, e a reprodução como nota de voz precisa ser conferida no
        aparelho antes de ligar o recurso. Um único POST: resultado ambíguo nunca é repetido por este provedor."""
        if not audio_base64 or not isinstance(audio_base64, str):
            raise ValueError("audio_base64 vazio")
        if audio_base64.startswith("data:"):
            raise ValueError("audio_base64 deve ser base64 puro, sem prefixo 'data:' (o Evolution recusa o prefixo)")
        s = get_settings()
        body: dict = {"number": normalize_phone(to), "audio": audio_base64}
        if s.evolution_voice_encoding is not None:
            body["encoding"] = bool(s.evolution_voice_encoding)
        if s.evolution_voice_delay_ms and s.evolution_voice_delay_ms > 0:
            body["delay"] = int(s.evolution_voice_delay_ms)
        return await self._post("message/sendWhatsAppAudio", body, instance=instance)

    async def send_location(
        self, to: str, latitude: float, longitude: float, caption: str = "", instance: str | None = None
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
            instance=instance,
        )

    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        # Evolution "messages.upsert" event: {event, instance, data: {key, pushName, message}}
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            return None  # malformed payload (e.g. "data": null) — not a crash
        key = data.get("key") or {}
        remote_jid = key.get("remoteJid")
        if not remote_jid:
            return None

        media_type, text = extract_baileys_content(data.get("message", {}) or {})

        return InboundMessage(
            phone=normalize_phone(str(remote_jid)),
            text=text,
            sender_name=str(data.get("pushName", "")),
            external_id=str(key.get("id", "")),
            media_type=media_type,
            # Review fix: the top-level "instance" field on the webhook
            # envelope (see this method's own comment above) was never
            # read -- every caller of inbound.instance was getting the
            # Pydantic default, which did not exist until base.py's fix.
            instance=str(payload.get("instance") or ""),
            # Review fix: this method used to discard every fromMe=True
            # event right here (`or key.get("fromMe"): return None`),
            # which made webhooks/router.py's entire owner-reply-capture
            # path (inbound.from_me -> _capture_human_reply) unreachable.
            # router.py is the one place that decides what to do with a
            # fromMe=True event (ignore it, or treat it as the owner
            # answering from his own phone) -- this method's only job is
            # to report what the webhook actually said.
            from_me=bool(key.get("fromMe")),
            # media_key is intentionally NOT populated: no extraction logic
            # exists for it in this payload shape, and no download_media
            # method exists on this provider to consume it either. Left as
            # None (the InboundMessage default) rather than guessed.
        )
