"""Cliente do serviço de voz (voice-service/). Falha = exceção tipada; quem chama decide (aqui: o texto já foi enviado)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

import httpx

from utils.config import get_settings


class VoiceError(Exception):
    """Base. `code` é estável para registro e testes."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class VoiceUnavailable(VoiceError):
    """Serviço fora do ar, ocupado, sem modelo pronto ou lento demais. Nada foi enviado ao cliente."""


class VoiceRejected(VoiceError):
    """O serviço recusou o pedido ou devolveu algo inaceitável (texto, perfil, hash, formato)."""


@dataclass(frozen=True)
class VoiceAudio:
    data: bytes
    sha256: str
    duration_seconds: float
    engine: str
    model_revision: str
    reference_sha256: str
    audio_id: str


# Mesmo contrato de voice-service/app/service.py (_REQUEST_ID): descoberto numa demonstração com o serviço REAL, em que um
# request_id curto ("voice-1") era recusado com 422 pelo esquema do serviço, embora os testes com transporte simulado passassem.
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,63}$")


_MAX_META_BYTES = 64 * 1024


async def _read_bounded(response: httpx.Response, limit: int, what: str) -> bytes:
    """Lê o corpo em fluxo e para ao ultrapassar `limit`, com ou sem Content-Length: um serviço defeituoso (ou comprometido) não
    consegue fazer o backend alocar memória sem limite."""
    declared = response.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise VoiceRejected("too_large", f"{what}: Content-Length {declared} acima do limite de {limit} bytes")
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise VoiceRejected("too_large", f"{what}: corpo acima do limite de {limit} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


async def synthesize(text: str, request_id: str, *, client: httpx.AsyncClient | None = None) -> VoiceAudio:
    s = get_settings()
    if not _REQUEST_ID.match(request_id or ""):
        raise VoiceRejected("bad_request_id", "request_id fora do contrato do serviço de voz (8 a 64 caracteres [A-Za-z0-9_.:-])")
    if not s.store_voice_url or not s.store_voice_token:
        raise VoiceUnavailable("not_configured", "serviço de voz não configurado")
    if not s.store_voice_url.startswith(("http://", "https://")):
        raise VoiceUnavailable("not_configured", "URL do serviço de voz inválida")
    headers = {"Authorization": f"Bearer {s.store_voice_token}"}
    timeout = httpx.Timeout(s.store_voice_timeout_seconds, connect=5.0)
    own = client is None
    http = client or httpx.AsyncClient(base_url=s.store_voice_url, timeout=timeout)
    try:
        try:
            async with http.stream("POST", "/v1/synthesize", headers=headers, json={"request_id": request_id, "text": text, "language": "pt"}) as r:
                status, ctype = r.status_code, r.headers.get("content-type", "")
                body = await _read_bounded(r, _MAX_META_BYTES, "resposta da síntese")
        except httpx.TimeoutException as exc:
            raise VoiceUnavailable("timeout", "tempo excedido no serviço de voz") from exc
        except httpx.HTTPError as exc:
            raise VoiceUnavailable("transport", f"{type(exc).__name__}") from exc
        if status in (429, 503, 504, 502, 500):
            code = None
            if ctype.startswith("application/json"):
                try:
                    code = json.loads(body).get("error", {}).get("code")
                except (ValueError, AttributeError):
                    code = None
            raise VoiceUnavailable(code or f"http_{status}", f"serviço de voz respondeu {status}")
        if status != 200:
            raise VoiceRejected(f"http_{status}", f"serviço de voz recusou o pedido ({status})")
        try:
            meta = json.loads(body)
            audio_id, expected = str(meta["audio_id"]), str(meta["sha256"])
            seconds = float(meta["duration_seconds"])
        except (ValueError, KeyError, TypeError) as exc:
            raise VoiceRejected("bad_metadata", "resposta do serviço de voz malformada") from exc
        try:
            async with http.stream("GET", f"/v1/audio/{audio_id}", headers=headers) as a:
                if a.status_code != 200:
                    raise VoiceRejected(f"http_{a.status_code}", "áudio indisponível no serviço de voz")
                data = await _read_bounded(a, s.store_voice_max_audio_bytes, "áudio")
        except httpx.TimeoutException as exc:
            raise VoiceUnavailable("timeout", "tempo excedido ao baixar o áudio") from exc
        except httpx.HTTPError as exc:
            raise VoiceUnavailable("transport", f"{type(exc).__name__}") from exc
        if hashlib.sha256(data).hexdigest() != expected:
            raise VoiceRejected("hash_mismatch", "o áudio recebido não confere com o SHA-256 informado")
        try:  # limpeza imediata no serviço; falha aqui não importa (há TTL)
            await http.delete(f"/v1/audio/{audio_id}", headers=headers)
        except httpx.HTTPError:
            pass
        return VoiceAudio(data, expected, seconds, str(meta.get("engine", "")), str(meta.get("model_revision", "")),
                          str(meta.get("reference_sha256", "")), audio_id)
    finally:
        if own:
            await http.aclose()
