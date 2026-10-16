"""Transcricao de audio via Groq (Whisper hospedado, API compativel com a da OpenAI).

Contrato: `providers/stt/base.py`. Falha NUNCA vira texto inventado: qualquer erro de rede/HTTP, audio grande demais, resposta vazia
ou transcricao que e so uma "alucinacao" tipica do Whisper levanta `STTProviderError` (o chamador ja trata isso como "sem
transcricao"). A chave de API so e lida das configuracoes (variavel de ambiente) e nunca entra em mensagem de erro ou log.
"""
from __future__ import annotations

import asyncio
import re
import unicodedata

import httpx

from providers.stt.base import STTProvider, STTProviderError
from utils.config import get_settings

# Limite de tamanho de arquivo da API de transcricao (plano gratuito); acima disso nem tentamos enviar.
MAX_AUDIO_BYTES = 25 * 1024 * 1024
_ATTEMPTS = 2  # transcricao nao tem efeito colateral: uma nova tentativa e segura; poucas, porque o webhook pode estar esperando
_RETRY_STATUS = {408, 429, 500, 502, 503, 504}
_MAX_RETRY_WAIT_SECONDS = 5.0

_EXTENSIONS = {
    "audio/ogg": "ogg", "audio/opus": "ogg", "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/mp4": "m4a", "audio/m4a": "m4a",
    "audio/x-m4a": "m4a", "audio/aac": "m4a", "audio/wav": "wav", "audio/x-wav": "wav", "audio/webm": "webm", "audio/flac": "flac",
}

# Saidas que o Whisper inventa em audio curto, mudo ou com ruido (a transcricao INTEIRA e uma destas = nao ha fala).
_HALLUCINATIONS = frozenset(
    {
        "legendas pela comunidade amara.org", "legendas pela comunidade", "amara.org", "obrigado por assistir",
        "obrigada por assistir", "inscreva-se no canal", "se inscreva no canal", "tchau tchau",
    }
)


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^\w\s.\-]", "", folded).strip(" .-\n\t")


def _extension(mime_type: str) -> str:
    base = (mime_type or "").split(";")[0].strip().lower()
    return _EXTENSIONS.get(base, "ogg")


class GroqSTTProvider(STTProvider):
    name = "groq"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        settings = get_settings()
        self._key = settings.groq_api_key
        self._url = settings.groq_base_url.rstrip("/") + "/audio/transcriptions"
        self._model = settings.groq_stt_model
        self._language = settings.groq_stt_language
        self._timeout = settings.groq_stt_timeout_seconds
        self._transport = transport  # so os testes injetam; em producao e sempre None

    @property
    def enabled(self) -> bool:
        return bool(self._key)

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        if not self.enabled:
            raise STTProviderError("Groq STT sem chave configurada")
        if not audio_bytes:
            raise STTProviderError("audio vazio")
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise STTProviderError("audio maior que o limite da API de transcricao")
        filename = f"audio.{_extension(mime_type)}"
        data = {"model": self._model, "temperature": "0", "response_format": "json"}
        if self._language:
            data["language"] = self._language
        last = "falha desconhecida"
        for attempt in range(1, _ATTEMPTS + 1):
            wait = 1.0 * attempt
            try:
                async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                    response = await client.post(
                        self._url,
                        headers={"Authorization": f"Bearer {self._key}"},
                        data=data,
                        files={"file": (filename, audio_bytes, mime_type or "application/octet-stream")},
                    )
            except httpx.HTTPError as exc:
                last = f"erro de rede ({type(exc).__name__})"
            else:
                if response.status_code == 200:
                    return self._parse(response)
                last = f"HTTP {response.status_code}: {self._error_message(response)}"
                if response.status_code not in _RETRY_STATUS:
                    break
                try:
                    wait = min(float(response.headers.get("retry-after", wait)), _MAX_RETRY_WAIT_SECONDS)
                except ValueError:
                    pass
            if attempt < _ATTEMPTS:
                await asyncio.sleep(wait)
        raise STTProviderError(f"Groq STT falhou: {last}")

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            error = response.json().get("error")
            message = error.get("message") if isinstance(error, dict) else error
        except (ValueError, AttributeError):
            message = None
        return str(message or "sem detalhe")[:200]

    @staticmethod
    def _parse(response: httpx.Response) -> str:
        try:
            text = str(response.json().get("text") or "").strip()
        except (ValueError, AttributeError):
            raise STTProviderError("Groq STT devolveu resposta invalida") from None
        if not text:
            raise STTProviderError("Groq STT devolveu transcricao vazia")
        if _normalize(text) in _HALLUCINATIONS:
            raise STTProviderError("transcricao parece alucinacao do Whisper (sem fala)")
        return text
