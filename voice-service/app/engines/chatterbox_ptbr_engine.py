"""Motor Chatterbox pt-BR (pacote oficial da Resemble: código do Space `Chatterbox-Multilingual-TTS-pt-br`).

Por que existe, ao lado de `chatterbox_engine.py`: o `chatterbox-tts` do PyPI só carrega o modelo multilíngue V2, que com a referência
do titular encerrava a fala depois de 0,5 a 1,5 s (detector de repetição) e dava sotaque. O som aprovado na escuta às cegas veio
do pacote pt-BR, cujo código é o do Space (sem esse detector) e que carrega `t3_pt_br.safetensors` + `s3gen_v3.pt`. Aquele código pede
outras versões de torch/transformers, por isso roda num ambiente Python SEPARADO (`.venv-ptbr`); este módulo não importa nada dele
até `load()`, e recusa o carregamento se já houver outro pacote `chatterbox` na memória (o do PyPI, por exemplo), para nunca misturar.

Os pesos NÃO são baixados aqui: o serviço roda offline e fixa o que carrega. `VOICE_MODEL_DIR` precisa conter `ve.pt`, o tokenizador,
`t3_pt_br.safetensors` e `s3gen_v3.pt` (`scripts/download_ptbr_weights.py` monta a pasta e imprime a revisão a registrar em
`VOICE_MODEL_REVISION`).

NÃO TESTADO NESTE REPOSITÓRIO COM PESOS REAIS (o desenvolvimento não alcança o Hugging Face): a API usada foi lida no código do Space
(`ChatterboxTTS.from_local`, `generate(text, audio_prompt_path, exaggeration, cfg_weight, temperature, language_id)`), os testes usam
um duplo, e a validação real é a escuta no PC do titular.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

from app.engines.base import Engine, EngineError, EngineNotReady, SynthesisResult

_VOICE_ENCODER = "ve.pt"


def _import_space_tts(space_dir: Path):
    """Importa `chatterbox.tts` do código do Space, sem aceitar outro pacote `chatterbox` já carregado."""
    src = space_dir / "chatterbox" / "src"
    if not (src / "chatterbox" / "tts.py").is_file():
        raise EngineNotReady(f"não achei {src / 'chatterbox' / 'tts.py'}: VOICE_PTBR_SPACE_DIR deve ser a pasta do Space baixado")
    loaded = sys.modules.get("chatterbox")
    if loaded is not None:
        origin = Path(getattr(loaded, "__file__", None) or "").resolve()
        if src.resolve() not in origin.parents:
            raise EngineNotReady(f"outro pacote 'chatterbox' já está carregado ({origin}); rode este motor no ambiente do pacote pt-BR")
    elif str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        from chatterbox import tts  # type: ignore
    except Exception as exc:  # noqa: BLE001 - dependências faltando no ambiente: motor indisponível, serviço de pé
        raise EngineNotReady(f"pacote pt-BR não importou: {type(exc).__name__}: {exc}") from exc
    return tts


class ChatterboxPtBrEngine(Engine):
    name = "chatterbox_ptbr"
    model_id = "ResembleAI/Chatterbox-Multilingual-pt-br (código do Space)"

    def __init__(self, settings) -> None:
        self._settings = settings
        self.model_revision = settings.model_revision
        self._model = None
        self._conds: dict[str, object] = {}

    def load(self) -> None:
        s = self._settings
        if not s.model_revision:
            raise EngineNotReady("VOICE_MODEL_REVISION vazio: registre a revisão dos pesos (use scripts/download_ptbr_weights.py)")
        if len(s.model_revision) > 64:  # o backend grava a revisão em coluna de 64 caracteres (store_voice_sends.model_revision)
            raise EngineNotReady("VOICE_MODEL_REVISION com mais de 64 caracteres: use o valor impresso por scripts/download_ptbr_weights.py")
        if s.ptbr_space_dir is None:
            raise EngineNotReady("VOICE_PTBR_SPACE_DIR não definido: aponte para a pasta do Space pt-BR baixado")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        tts = _import_space_tts(Path(s.ptbr_space_dir))
        model_dir = Path(s.model_dir)
        required = (_VOICE_ENCODER, tts.TOKENIZER_FILENAME, tts.T3_FILENAME, tts.S3GEN_FILENAME)
        missing = [f for f in required if not (model_dir / f).is_file()]
        if missing:
            raise EngineNotReady(f"pesos ausentes em {model_dir}: {', '.join(missing)}")
        try:
            self._model = tts.ChatterboxTTS.from_local(
                model_dir, s.device, t3_filename=tts.T3_FILENAME, s3gen_filename=tts.S3GEN_FILENAME,
            )
        except Exception as exc:  # noqa: BLE001
            raise EngineNotReady(f"falha ao carregar os pesos pt-BR: {type(exc).__name__}: {exc}") from exc

    def synthesize(self, text: str, language: str, reference: Path, reference_text: str | None) -> SynthesisResult:
        if self._model is None:
            raise EngineNotReady("modelo não carregado")
        s = self._settings
        cfg, exg, temp = float(s.chatterbox_cfg_weight), float(s.chatterbox_exaggeration), float(s.chatterbox_temperature)
        key = f"{reference}|{exg}"  # a conditional depende da referência E da expressividade
        try:
            if key not in self._conds:
                self._model.prepare_conditionals(str(reference), exaggeration=exg)
                self._conds[key] = self._model.conds
            self._model.conds = self._conds[key]
            wav = self._model.generate(text, language_id=language, exaggeration=exg, cfg_weight=cfg, temperature=temp)
        except Exception as exc:  # noqa: BLE001
            raise EngineError(f"{type(exc).__name__}: {exc}") from exc
        samples = np.asarray(wav.squeeze().detach().cpu().numpy(), dtype=np.float32)
        return SynthesisResult(samples, int(self._model.sr))
