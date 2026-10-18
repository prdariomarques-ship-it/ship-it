"""Motor ElevenLabs (síntese na nuvem com a voz clonada na conta do titular).

Diferenças deliberadas em relação aos motores locais:
- NÃO usa a gravação de referência do perfil: a voz é a `VOICE_ELEVENLABS_VOICE_ID` (clonada na conta ElevenLabs a partir de gravações
  do titular, com o consentimento dele). O perfil local continua exigido pelo serviço (consentimento, autorização por agente).
- O texto da resposta SAI da máquina para a ElevenLabs. Só habilite com o titular ciente (LGPD/consentimento) e para conteúdo que possa sair.
- A chave da API nunca é logada nem entra em mensagem de erro; prefira `VOICE_ELEVENLABS_API_KEY_FILE` (arquivo fora do repositório).
- Pede `pcm_24000` (PCM 16 bits mono, sem cabeçalho): entra direto no mesmo caminho numpy -> pós-processamento -> Opus dos outros motores.

Parâmetros da API conforme a documentação pública da ElevenLabs lida de memória do fornecedor (POST /v1/text-to-speech/{voice_id},
cabeçalho xi-api-key, corpo text/model_id/voice_settings, query output_format). NÃO validado contra a API real neste repositório
(sem acesso de rede a ela); a validação é a primeira chamada no PC do titular (`scripts/make_samples.py`). Erros 4xx trazem o corpo
(truncado) para tornar divergências visíveis.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import numpy as np

from app.engines.base import Engine, EngineError, EngineNotReady, SynthesisResult

SAMPLE_RATE = 24000
_OUTPUT_FORMAT = "pcm_24000"
_VOICE_ID = re.compile(r"^[A-Za-z0-9]{10,40}$")
# Modelos que aceitam `language_code` no corpo (nos demais a API recusa o campo).
_LANGUAGE_CODE_MODELS = frozenset({"eleven_flash_v2_5", "eleven_turbo_v2_5"})
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ERROR_BODY = 300


def _read_key(settings) -> str:
    key_file = getattr(settings, "elevenlabs_api_key_file", None)
    if key_file:
        path = Path(key_file)
        try:
            key = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise EngineNotReady(f"não consegui ler VOICE_ELEVENLABS_API_KEY_FILE ({path}): {type(exc).__name__}") from exc
    else:
        secret = getattr(settings, "elevenlabs_api_key", None)
        key = secret.get_secret_value().strip() if secret is not None else ""
    if not key:
        raise EngineNotReady("chave ElevenLabs ausente: defina VOICE_ELEVENLABS_API_KEY_FILE (preferido) ou VOICE_ELEVENLABS_API_KEY")
    if any(c.isspace() for c in key):
        raise EngineNotReady("chave ElevenLabs inválida (contém espaço/quebra de linha no meio)")
    return key


class ElevenLabsEngine(Engine):
    name = "elevenlabs"

    def __init__(self, settings, *, client=None, sleep=time.sleep) -> None:
        self._s = settings
        self._client = client  # injetável nos testes (httpx.Client com MockTransport)
        self._sleep = sleep
        self._key = ""
        self.model_id = f"elevenlabs/{settings.elevenlabs_model_id}"
        self.model_revision = settings.elevenlabs_voice_id[:64]  # a revisão auditável aqui é a voz usada

    def load(self) -> None:
        s = self._s
        if not _VOICE_ID.match(s.elevenlabs_voice_id or ""):
            raise EngineNotReady("VOICE_ELEVENLABS_VOICE_ID ausente ou inválido (copie o voice_id da voz clonada na ElevenLabs)")
        self._key = _read_key(s)
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:  # pragma: no cover - httpx está em requirements.txt
                raise EngineNotReady("httpx não instalado") from exc
            self._client = httpx.Client(base_url=s.elevenlabs_base_url, timeout=s.elevenlabs_timeout_seconds)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    # ------------------------------------------------------------------------------------------------
    def _payload(self, text: str, language: str) -> dict:
        s = self._s
        body: dict = {
            "text": text,
            "model_id": s.elevenlabs_model_id,
            "voice_settings": {
                "stability": s.elevenlabs_stability,
                "similarity_boost": s.elevenlabs_similarity,
                "style": s.elevenlabs_style,
                "use_speaker_boost": s.elevenlabs_speaker_boost,
                "speed": s.elevenlabs_speed,
            },
        }
        if s.elevenlabs_model_id in _LANGUAGE_CODE_MODELS and language:
            body["language_code"] = language
        return body

    def _describe(self, resp) -> str:
        body = (resp.text or "").strip().replace("\n", " ")
        if self._key:
            body = body.replace(self._key, "***")
        body = body[:_MAX_ERROR_BODY]
        return f"HTTP {resp.status_code}: {body}" if body else f"HTTP {resp.status_code}"

    def synthesize(self, text: str, language: str, reference: Path, reference_text: str | None) -> SynthesisResult:
        if self._client is None or not self._key:
            raise EngineNotReady("motor ElevenLabs não carregado")
        import httpx

        s = self._s
        url = f"/v1/text-to-speech/{s.elevenlabs_voice_id}"
        headers = {"xi-api-key": self._key, "Content-Type": "application/json", "Accept": "audio/pcm"}
        payload = self._payload(text, language)
        attempts = 1 + s.elevenlabs_max_retries
        last = "sem resposta"
        for attempt in range(attempts):
            try:
                resp = self._client.post(url, params={"output_format": _OUTPUT_FORMAT}, headers=headers, json=payload)
            except httpx.TimeoutException:
                last = "tempo esgotado"
            except httpx.TransportError as exc:
                last = f"falha de rede ({type(exc).__name__})"
            else:
                if resp.status_code == 200:
                    return self._decode(resp.content)
                last = self._describe(resp)
                if resp.status_code in (401, 403):
                    raise EngineError(f"ElevenLabs recusou a chave/permissão ({last})")
                if resp.status_code == 402:
                    raise EngineError(f"ElevenLabs sem créditos/plano insuficiente ({last})")
                if resp.status_code not in _RETRY_STATUS:
                    raise EngineError(f"ElevenLabs recusou a requisição ({last})")
            if attempt + 1 < attempts:
                self._sleep(min(2.0 ** attempt, 8.0))
        raise EngineError(f"ElevenLabs indisponível após {attempts} tentativa(s): {last}")

    @staticmethod
    def _decode(raw: bytes) -> SynthesisResult:
        if len(raw) < 2:
            raise EngineError("ElevenLabs devolveu áudio vazio")
        if len(raw) % 2:
            raw = raw[:-1]
        pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        return SynthesisResult(samples=pcm, sample_rate=SAMPLE_RATE)
