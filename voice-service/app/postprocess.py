"""Pós-processamento opcional do áudio GERADO (nunca da gravação de referência): pausas, ritmo e brilho.

Motivo (escuta de 17/10/2026): o Chatterbox gera pausas longas entre frases (39-44% de silêncio) e uma voz com pouca energia acima de ~1 kHz
(95% da energia abaixo de 690 Hz), o que soa "em câmera lenta" e abafado. Tudo aqui é DESLIGADO por padrão (`identity` devolve o mesmo
array); cada etapa é ligada por variável de ambiente `VOICE_POST_*` e validada na escuta antes de qualquer uso em produção.

Ordem: encurtar pausas -> ritmo (atempo, preserva o tom) -> brilho (passa-alta 70 Hz + realce de presença + prateleira de agudos).
"""
from __future__ import annotations

import av
import numpy as np

FRAME_S = 0.02
SILENCE_THRESHOLD = 0.06      # relativo ao percentil 95 da energia por quadro (mesmo critério de scripts/compact_pauses.py)
MIN_PAUSE_S = 0.30
KEEP_PAUSE_S = 0.12


def compact_pauses(x: np.ndarray, sr: int) -> np.ndarray:
    """Pausas acima de MIN_PAUSE_S perdem o miolo (ficam KEEP_PAUSE_S de cada lado; nas pontas, só o lado interno). A fala é copiada."""
    fr = int(sr * FRAME_S)
    m = len(x) // fr
    if m == 0:
        return x
    frames = x[: m * fr].reshape(m, fr)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    ref = float(np.percentile(rms, 95))
    if ref <= 0.0:
        return x
    sil = rms < SILENCE_THRESHOLD * ref
    keep_n, min_n = max(1, round(KEEP_PAUSE_S / FRAME_S)), round(MIN_PAUSE_S / FRAME_S)
    parts: list[np.ndarray] = []
    i = 0
    while i < m:
        j = i
        while j < m and sil[j] == sil[i]:
            j += 1
        run = frames[i:j]
        if sil[i] and (j - i) > min_n:
            head, tail = frames[i : i + keep_n], frames[j - keep_n : j]
            run = tail if i == 0 else head if j == m else np.concatenate([head, tail])
        parts.append(run.reshape(-1))
        i = j
    parts.append(x[m * fr :])  # sobra menor que um quadro
    return np.concatenate(parts).astype(np.float32)


def _filter(x: np.ndarray, sr: int, chain: list[tuple[str, str]]) -> np.ndarray:
    g = av.filter.Graph()
    src = g.add_abuffer(format="flt", sample_rate=sr, layout="mono", time_base=f"1/{sr}")
    nodes = [g.add(name, args) for name, args in chain]
    sink = g.add("abuffersink")
    prev = src
    for node in nodes:
        prev.link_to(node)
        prev = node
    prev.link_to(sink)
    g.configure()
    frame = av.AudioFrame.from_ndarray(np.ascontiguousarray(x.reshape(1, -1), dtype=np.float32), format="flt", layout="mono")
    frame.sample_rate = sr
    frame.pts = 0
    src.push(frame)
    src.push(None)
    out: list[np.ndarray] = []
    while True:
        try:
            out.append(sink.pull().to_ndarray().reshape(-1))
        except (av.error.EOFError, av.error.BlockingIOError):
            break
    return np.concatenate(out).astype(np.float32) if out else x


def brightness_chain(db: float) -> list[tuple[str, str]]:
    """Presença (3 kHz) e prateleira de agudos (4,5 kHz) com o mesmo ganho `db`; 3 dB = variante "suave" aprovada para teste."""
    return [("highpass", "f=70"), ("equalizer", f"f=3000:t=q:w=1:g={db:g}"), ("treble", f"g={db:g}:f=4500")]


def postprocess(samples: np.ndarray, sr: int, *, compact: bool = False, tempo: float = 1.0, brightness_db: float = 0.0) -> np.ndarray:
    """Devolve `samples` (o MESMO objeto) quando nada está ligado; caso contrário, um novo array float32 mono."""
    if not compact and tempo == 1.0 and brightness_db == 0.0:
        return samples
    x = np.asarray(samples, dtype=np.float32).reshape(-1)
    if compact:
        x = compact_pauses(x, sr)
    chain: list[tuple[str, str]] = []
    if tempo != 1.0:
        chain.append(("atempo", f"{tempo:g}"))
    if brightness_db != 0.0:
        chain.extend(brightness_chain(brightness_db))
    return _filter(x, sr, chain) if chain else x
