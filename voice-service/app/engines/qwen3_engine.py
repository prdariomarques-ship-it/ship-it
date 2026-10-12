"""Motor Qwen3-TTS Base (Qwen/Alibaba). Código Apache-2.0; português e clonagem com áudio + transcrição de referência.

NÃO TESTADO NESTE REPOSITÓRIO COM PESOS REAIS (host dos pesos inacessível no ambiente de desenvolvimento). A integração
segue a API de qwen-tts 0.1.1 (Qwen3TTSModel.from_pretrained / create_voice_clone_prompt / generate_voice_clone). Exige
`reference_text` no perfil (transcrição exata da referência) para o modo de clonagem com contexto.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.engines.base import Engine, EngineError, EngineNotReady, SynthesisResult

_LANG = {"pt": "Portuguese"}


class Qwen3Engine(Engine):
    name = "qwen3tts"
    model_id = "Qwen/Qwen3-TTS-12Hz Base"

    def __init__(self, settings) -> None:
        self._settings = settings
        self.model_revision = settings.model_revision
        self._model = None
        self._prompts: dict[str, object] = {}

    def load(self) -> None:
        s = self._settings
        if not s.model_revision:
            raise EngineNotReady("VOICE_MODEL_REVISION vazio: fixe o commit dos pesos (não use 'main')")
        model_dir = Path(s.model_dir)
        if not (model_dir / "config.json").is_file():
            raise EngineNotReady(f"pesos ausentes em {model_dir} (config.json)")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        try:
            import torch  # type: ignore
            from qwen_tts import Qwen3TTSModel  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise EngineNotReady(f"qwen-tts não instalado: {type(exc).__name__}") from exc
        try:
            dtype = torch.bfloat16 if s.device.startswith("cuda") else torch.float32
            self._model = Qwen3TTSModel.from_pretrained(str(model_dir), device_map=s.device, dtype=dtype)
        except Exception as exc:  # noqa: BLE001
            raise EngineNotReady(f"falha ao carregar os pesos: {type(exc).__name__}: {exc}") from exc

    def synthesize(self, text: str, language: str, reference: Path, reference_text: str | None) -> SynthesisResult:
        if self._model is None:
            raise EngineNotReady("modelo não carregado")
        if language not in _LANG:
            raise EngineError(f"idioma não suportado por este adaptador: {language!r}")
        if not reference_text:
            raise EngineError("perfil sem reference_text: o Qwen3-TTS exige a transcrição da referência")
        key = str(reference)
        try:
            if key not in self._prompts:
                self._prompts[key] = self._model.create_voice_clone_prompt(ref_audio=str(reference), ref_text=reference_text)
            wavs, sr = self._model.generate_voice_clone(
                text=text, language=_LANG[language], voice_clone_prompt=self._prompts[key]
            )
        except Exception as exc:  # noqa: BLE001
            raise EngineError(f"{type(exc).__name__}: {exc}") from exc
        return SynthesisResult(wavs[0], int(sr))
