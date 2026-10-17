#!/usr/bin/env python3
"""Encurta as pausas longas de uma gravação de referência (WAV PCM 16 bits), sem filtro, ganho ou normalização.

Motivo (rodada de 17/10/2026): o Chatterbox copia o RITMO da referência. A gravação do titular tinha 58% de silêncio, com pausas de
até 2 s, e todas as variações geradas saíram em "slow motion". Com as pausas acima de 0,30 s reduzidas para 0,20 s (silêncio de 58%
para 26%) a fala saiu mais rápida e passou na escuta. As amostras de fala são COPIADAS sem alteração; só o silêncio é cortado.
O arquivo original não é tocado (o destino é outro arquivo). Se a referência virar o perfil de voz, o `original/` do perfil guardará
ESTE arquivo: mantenha a gravação bruta à parte.

  python -m scripts.compact_pauses ORIGINAL.wav DESTINO.wav [--max-seconds 12] [--min-pause 0.30] [--keep 0.10] [--threshold 0.06]
"""
from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

FRAME_S = 0.02


def read_wav_mono16(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"WAV precisa ser PCM de 16 bits (sampwidth={w.getsampwidth()})")
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype="<i2")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1).astype(np.int16)
    return x.astype(np.int16), sr


def silence_mask(x: np.ndarray, sr: int, threshold: float) -> tuple[np.ndarray, int]:
    """(máscara de quadros silenciosos, amostras por quadro). Limiar relativo ao percentil 95 da energia dos quadros."""
    fr = int(sr * FRAME_S)
    m = len(x) // fr
    if m == 0:
        raise ValueError("áudio curto demais")
    rms = np.sqrt((x[: m * fr].astype(np.float32).reshape(m, fr) ** 2).mean(axis=1))
    ref = float(np.percentile(rms, 95))
    if ref <= 0.0:
        raise ValueError("áudio sem sinal (silêncio total)")
    return rms < threshold * ref, fr


def compact_pauses(
    x: np.ndarray, sr: int, *, threshold: float = 0.06, min_pause: float = 0.30, keep: float = 0.10, max_seconds: float | None = None,
) -> np.ndarray:
    """Cada pausa mais longa que `min_pause` perde o miolo: ficam `keep` s de cada lado (no início/fim do arquivo, só o lado interno)."""
    if keep * 2 > min_pause:
        raise ValueError("2*keep não pode passar de min_pause (a 'compactação' aumentaria a pausa)")
    sil, fr = silence_mask(x, sr, threshold)
    m = len(sil)
    frames = x[: m * fr].reshape(m, fr)
    keep_n, min_n = max(1, round(keep / FRAME_S)), round(min_pause / FRAME_S)
    parts: list[np.ndarray] = []
    i = 0
    while i < m:
        j = i
        while j < m and sil[j] == sil[i]:
            j += 1
        run = frames[i:j]
        if sil[i] and (j - i) > min_n:
            head, tail = frames[i : i + keep_n], frames[j - keep_n : j]
            if i == 0:
                run = tail
            elif j == m:
                run = head
            else:
                run = np.concatenate([head, tail])
        parts.append(run.reshape(-1))
        i = j
    y = np.concatenate(parts)
    if max_seconds is not None:
        y = y[: int(max_seconds * sr)]
    return y.astype("<i2")


def write_wav_mono16(path: Path, y: np.ndarray, sr: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(y.astype("<i2").tobytes())


def silence_fraction(x: np.ndarray, sr: int, threshold: float = 0.06) -> float:
    sil, _ = silence_mask(x, sr, threshold)
    return float(sil.mean())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("origem", type=Path)
    ap.add_argument("destino", type=Path)
    ap.add_argument("--max-seconds", type=float, default=12.0)
    ap.add_argument("--min-pause", type=float, default=0.30)
    ap.add_argument("--keep", type=float, default=0.10)
    ap.add_argument("--threshold", type=float, default=0.06)
    ns = ap.parse_args(argv)
    if ns.origem.resolve() == ns.destino.resolve():
        raise SystemExit("o destino não pode ser o próprio arquivo de origem")
    try:
        x, sr = read_wav_mono16(ns.origem)
        y = compact_pauses(x, sr, threshold=ns.threshold, min_pause=ns.min_pause, keep=ns.keep, max_seconds=ns.max_seconds)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    write_wav_mono16(ns.destino, y, sr)
    print(f"original: {len(x) / sr:.1f} s ({silence_fraction(x, sr):.0%} silêncio) | compacta: {len(y) / sr:.1f} s ({silence_fraction(y, sr):.0%} silêncio)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
