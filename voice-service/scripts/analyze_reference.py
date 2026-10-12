"""Análise (somente leitura) de uma gravação de referência: volume, ruído, distorção e janela sugerida.

NÃO altera, filtra nem regrava nada. Serve para o proprietário e o engenheiro decidirem, com números, qual trecho usar
(`prepare_reference.py --start/--end`). Aceita qualquer formato que o PyAV/FFmpeg leia (ogg/opus do WhatsApp, wav, m4a...).

Uso: python scripts/analyze_reference.py ARQUIVO [--window 12] [--json]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import av
import numpy as np

FRAME_S = 0.05


def load_mono(path: Path) -> tuple[np.ndarray, int, dict]:
    container = av.open(str(path))
    try:
        stream = container.streams.audio[0]
        sr = int(stream.codec_context.sample_rate)
        info = {"codec": stream.codec_context.name, "container": container.format.name,
                "channels_in_file": int(stream.codec_context.channels), "sample_rate_hz": sr}
        chunks = []
        for frame in container.decode(stream):
            arr = frame.to_ndarray().astype(np.float32)
            if arr.dtype.kind in "iu":
                arr = arr / 32768.0
            if frame.format.is_planar:
                arr = arr.mean(axis=0)
            else:
                ch = len(frame.layout.channels)
                arr = arr.reshape(-1, ch).mean(axis=1) if ch > 1 else arr.reshape(-1)
            chunks.append(arr)
    finally:
        container.close()
    if not chunks:
        raise ValueError("arquivo sem áudio decodificável")
    x = np.concatenate(chunks)
    if np.abs(x).max() > 1.5:  # formatos inteiros sem normalização
        x = x / 32768.0
    return x, sr, info


def db(v: float) -> float:
    return 20 * math.log10(max(v, 1e-9))


def frame_rms(x: np.ndarray, sr: int) -> np.ndarray:
    n = int(FRAME_S * sr)
    k = len(x) // n
    if k == 0:
        return np.array([float(np.sqrt(np.mean(x ** 2)))])
    return np.sqrt(np.mean(x[: k * n].reshape(k, n) ** 2, axis=1))


def analyze(x: np.ndarray, sr: int, window_s: float = 12.0) -> dict:
    peak = float(np.max(np.abs(x)))
    rms_frames = frame_rms(x, sr)
    noise_floor = float(np.percentile(rms_frames, 10))
    loud = float(np.percentile(rms_frames, 90))
    speech_thr = max(noise_floor * 3.0, 10 ** (-45 / 20))
    speech = rms_frames > speech_thr
    clip_frac = float(np.mean(np.abs(x) >= 0.999))
    spec = np.abs(np.fft.rfft(x[: min(len(x), sr * 60)] * np.hanning(min(len(x), sr * 60)))) ** 2
    freqs = np.fft.rfftfreq(min(len(x), sr * 60), 1 / sr)
    cum = np.cumsum(spec) / max(spec.sum(), 1e-12)
    hum = {}
    for f0 in (50, 60):
        band = (freqs > f0 - 2) & (freqs < f0 + 2)
        around = ((freqs > f0 - 20) & (freqs < f0 - 5)) | ((freqs > f0 + 5) & (freqs < f0 + 20))
        hum[f"{f0}hz_db_above_neighbors"] = round(10 * math.log10(max(spec[band].mean(), 1e-12) / max(spec[around].mean(), 1e-12)), 1) if band.any() and around.any() else None
    report = {
        "duration_seconds": round(len(x) / sr, 2),
        "peak_dbfs": round(db(peak), 1),
        "rms_speech_dbfs": round(db(float(np.sqrt(np.mean(rms_frames[speech] ** 2)))) if speech.any() else -120.0, 1),
        "noise_floor_dbfs": round(db(noise_floor), 1),
        "snr_estimate_db": round(db(loud) - db(noise_floor), 1),
        "clipping_fraction": round(clip_frac, 6),
        "dc_offset": round(float(np.mean(x)), 5),
        "speech_ratio": round(float(speech.mean()), 3),
        "rolloff_95_hz": int(freqs[np.searchsorted(cum, 0.95)]) if len(freqs) else None,
        "mains_hum": hum,
        "flags": [],
    }
    f = report["flags"]
    if report["peak_dbfs"] > -1.0 or clip_frac > 1e-4:
        f.append("possível distorção/clipping")
    if report["rms_speech_dbfs"] < -32:
        f.append("volume de fala baixo")
    if report["snr_estimate_db"] < 20:
        f.append("relação sinal/ruído estimada baixa")
    if report["rolloff_95_hz"] is not None and report["rolloff_95_hz"] < 3500:
        f.append("banda estreita (pouco conteúdo agudo)")
    if report["duration_seconds"] < 6:
        f.append("referência curta")
    for k, v in hum.items():
        if v is not None and v > 10:
            f.append(f"possível zumbido de rede ({k})")
    report["suggested_window"] = suggest_window(x, sr, rms_frames, speech, window_s)
    return report


def suggest_window(x: np.ndarray, sr: int, rms_frames: np.ndarray, speech: np.ndarray, window_s: float) -> dict | None:
    n_win = int(window_s / FRAME_S)
    if len(rms_frames) < n_win:
        return None
    best, best_score = None, -1e9
    step = max(1, int(1.0 / FRAME_S))
    for start in range(0, len(rms_frames) - n_win + 1, step):
        seg = slice(start, start + n_win)
        ratio = float(speech[seg].mean())
        samples = x[int(start * FRAME_S * sr): int((start + n_win) * FRAME_S * sr)]
        clip = float(np.mean(np.abs(samples) >= 0.999))
        floor = float(np.percentile(rms_frames[seg], 10))
        voiced = rms_frames[seg][speech[seg]]
        level = db(float(np.sqrt(np.mean(voiced ** 2)))) if voiced.size else -120
        score = ratio * 10 - 1000 * clip - max(0.0, db(floor) + 60) * 0.2 - abs(level + 22) * 0.1
        if score > best_score:
            best, best_score = start, score
    return {"start_seconds": round(best * FRAME_S, 2), "end_seconds": round((best + n_win) * FRAME_S, 2),
            "note": "sugestão por critério objetivo; confirme ouvindo antes de usar"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("arquivo", type=Path)
    ap.add_argument("--window", type=float, default=12.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    x, sr, info = load_mono(args.arquivo)
    report = {"arquivo": args.arquivo.name, **info, **analyze(x, sr, args.window)}
    print(json.dumps(report, ensure_ascii=False, indent=None if args.json else 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
