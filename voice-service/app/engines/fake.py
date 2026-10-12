"""Motor DE TESTE: gera um sinal determinístico (NÃO é fala, NÃO imita voz alguma).

Existe só para exercitar fila, limites, formato e entrega sem pesos de modelo. É recusado a menos que
VOICE_ALLOW_FAKE_ENGINE=true, e nunca deve produzir as amostras ouvidas pelo proprietário.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import numpy as np

from app.engines.base import Engine, EngineError, SynthesisResult


class FakeEngine(Engine):
    name = "fake"
    model_id = "fake-test-signal"
    model_revision = "n/a"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.delay = 0.0
        self.fail_with: Exception | None = None
        self.seconds_per_char = 0.05
        self.sample_rate = 24000
        self.loaded = False

    def load(self) -> None:
        self.loaded = True

    def synthesize(self, text: str, language: str, reference: Path, reference_text: str | None) -> SynthesisResult:
        self.calls.append(text)
        if self.delay:
            time.sleep(self.delay)
        if self.fail_with is not None:
            raise self.fail_with
        if not reference.exists():
            raise EngineError("referência ausente")
        seconds = max(0.5, len(text) * self.seconds_per_char)
        n = int(seconds * self.sample_rate)
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big")
        freq = 180 + seed % 120
        t = np.arange(n) / self.sample_rate
        env = np.minimum(1.0, np.minimum(t, seconds - t) * 20)
        return SynthesisResult((0.25 * env * np.sin(2 * np.pi * freq * t)).astype(np.float32), self.sample_rate)
