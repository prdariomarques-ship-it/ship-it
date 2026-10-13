"""Motor Chatterbox Multilingual (Resemble AI). Código MIT; português ('pt') e clonagem por áudio de referência.

NÃO TESTADO NESTE REPOSITÓRIO COM PESOS REAIS: o ambiente de desenvolvimento não tinha acesso ao host dos pesos.
A integração segue a API de chatterbox-tts 0.1.7 (ChatterboxMultilingualTTS.from_local / prepare_conditionals /
generate(text, language_id, ...)). Os pesos precisam estar em VOICE_MODEL_DIR (download feito fora do serviço, com
revisão fixada) e o serviço roda offline (HF_HUB_OFFLINE=1).
"""
from __future__ import annotations

import os
from pathlib import Path

from app.engines.base import Engine, EngineError, EngineNotReady, SynthesisResult

_REQUIRED_FILES = ("ve.pt", "t3_mtl23ls_v2.safetensors", "s3gen.pt", "grapheme_mtl_merged_expanded_v1.json")


class ChatterboxEngine(Engine):
    name = "chatterbox"
    model_id = "ResembleAI/chatterbox (multilingual)"

    def __init__(self, settings) -> None:
        self._settings = settings
        self.model_revision = settings.model_revision
        self._model = None
        self._conds: dict[str, object] = {}

    def load(self) -> None:
        s = self._settings
        if not s.model_revision:
            raise EngineNotReady("VOICE_MODEL_REVISION vazio: fixe o commit dos pesos (não use 'main')")
        model_dir = Path(s.model_dir)
        missing = [f for f in _REQUIRED_FILES if not (model_dir / f).is_file()]
        if missing:
            raise EngineNotReady(f"pesos ausentes em {model_dir}: {', '.join(missing)}")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise EngineNotReady(f"chatterbox-tts não instalado: {type(exc).__name__}") from exc
        try:
            self._model = ChatterboxMultilingualTTS.from_local(model_dir, s.device)
        except Exception as exc:  # noqa: BLE001
            raise EngineNotReady(f"falha ao carregar os pesos: {type(exc).__name__}: {exc}") from exc

    def synthesize(self, text: str, language: str, reference: Path, reference_text: str | None) -> SynthesisResult:
        if self._model is None:
            raise EngineNotReady("modelo não carregado")
        s = self._settings
        cfg, exg = float(s.chatterbox_cfg_weight), float(s.chatterbox_exaggeration)
        key = f"{reference}|{exg}"                                   # a conditional depende da referência E da expressividade
        try:
            if key not in self._conds:
                self._model.prepare_conditionals(str(reference), exaggeration=exg)
                self._conds[key] = self._model.conds
            self._model.conds = self._conds[key]
            wav = self._model.generate(text, language_id=language, exaggeration=exg, cfg_weight=cfg)
        except Exception as exc:  # noqa: BLE001
            raise EngineError(f"{type(exc).__name__}: {exc}") from exc
        samples = wav.squeeze().detach().cpu().numpy()
        return SynthesisResult(samples, int(self._model.sr))
