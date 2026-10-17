"""Contrato dos motores de síntese. Cada motor é carregado uma vez e usado por um único thread por vez."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class EngineError(RuntimeError):
    """Falha da síntese em si (modelo, memória, entrada recusada pelo modelo)."""


class EngineNotReady(EngineError):
    """O motor não pode atender agora (pesos ausentes, revisão não fixada, dependência faltando)."""


@dataclass(frozen=True)
class SynthesisResult:
    samples: np.ndarray  # float32 mono
    sample_rate: int


class Engine(ABC):
    name: str = "base"
    # Versões/identidade registradas em cada resposta e nas medições (auditoria).
    model_id: str = ""
    model_revision: str = ""

    @abstractmethod
    def load(self) -> None:
        """Carrega o modelo (lento). Levanta EngineNotReady se não for possível."""

    @abstractmethod
    def synthesize(self, text: str, language: str, reference: Path, reference_text: str | None) -> SynthesisResult:
        """Gera fala. Não é thread-safe: o chamador serializa por motor."""

    def close(self) -> None:  # pragma: no cover - opcional
        return None


def build_engine(settings) -> Engine:
    name = settings.engine
    if name == "fake":
        if not settings.allow_fake_engine:
            raise EngineNotReady("motor 'fake' é só para testes: defina VOICE_ALLOW_FAKE_ENGINE=true")
        from app.engines.fake import FakeEngine
        return FakeEngine()
    if name == "chatterbox":
        from app.engines.chatterbox_engine import ChatterboxEngine
        return ChatterboxEngine(settings)
    if name == "chatterbox_ptbr":
        from app.engines.chatterbox_ptbr_engine import ChatterboxPtBrEngine
        return ChatterboxPtBrEngine(settings)
    if name == "qwen3tts":
        from app.engines.qwen3_engine import Qwen3Engine
        return Qwen3Engine(settings)
    raise EngineNotReady(f"motor desconhecido: {name!r}")
