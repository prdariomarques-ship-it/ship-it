"""Codificação e validação do áudio de saída: OGG/Opus mono 48 kHz, o formato de mensagem de voz do WhatsApp.

Só o áudio GERADO passa por aqui. A gravação de referência nunca é alterada por este módulo.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass

import av
import numpy as np

OPUS_RATE = 48000


class AudioFormatError(ValueError):
    """Áudio fora do formato aceito para mensagem de voz."""


@dataclass(frozen=True)
class AudioInfo:
    container: str
    codec: str
    sample_rate: int
    channels: int
    duration_seconds: float
    peak_dbfs: float


def _to_mono_float32(samples: np.ndarray) -> np.ndarray:
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim == 2:  # (canais, amostras) ou (amostras, canais): reduz para mono pela média
        x = x.mean(axis=0 if x.shape[0] <= 8 and x.shape[0] < x.shape[1] else 1)
    if x.ndim != 1 or x.size == 0:
        raise AudioFormatError("áudio vazio ou com dimensões inválidas")
    if not np.all(np.isfinite(x)):
        raise AudioFormatError("áudio com valores não finitos (NaN/Inf)")
    return x


def limit_peak(x: np.ndarray, target_dbfs: float) -> np.ndarray:
    """Só ATENUA quando o pico passa do alvo (evita clipping). Nunca amplifica nem filtra."""
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    ceiling = 10 ** (target_dbfs / 20.0)
    if peak > ceiling > 0:
        return (x * (ceiling / peak)).astype(np.float32)
    return x


def encode_ogg_opus(samples: np.ndarray, sample_rate: int, bitrate: int = 28000, peak_dbfs: float = -3.0) -> bytes:
    if sample_rate < 8000 or sample_rate > 96000:
        raise AudioFormatError(f"taxa de amostragem fora do intervalo aceito: {sample_rate}")
    x = limit_peak(_to_mono_float32(samples), peak_dbfs)
    buf = io.BytesIO()
    container = av.open(buf, "w", format="ogg")
    try:
        stream = container.add_stream("libopus", rate=OPUS_RATE)
        stream.layout = "mono"
        stream.bit_rate = bitrate
        resampler = av.AudioResampler(format="flt", layout="mono", rate=OPUS_RATE)
        frame = av.AudioFrame.from_ndarray(x.reshape(1, -1), format="flt", layout="mono")
        frame.sample_rate = int(sample_rate)
        for f in resampler.resample(frame):
            for packet in stream.encode(f):
                container.mux(packet)
        for f in resampler.resample(None) or []:
            for packet in stream.encode(f):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    finally:
        container.close()
    return buf.getvalue()


def probe_ogg_opus(data: bytes) -> AudioInfo:
    """Decodifica de verdade (não confia em cabeçalho) e exige OGG + Opus + mono. Levanta AudioFormatError."""
    if not data or data[:4] != b"OggS":
        raise AudioFormatError("não é um contêiner OGG")
    try:
        container = av.open(io.BytesIO(data), format="ogg")
    except Exception as exc:  # noqa: BLE001 - qualquer falha de leitura = formato inválido
        raise AudioFormatError(f"OGG ilegível: {type(exc).__name__}") from exc
    try:
        if len(container.streams.audio) != 1 or container.streams.video:
            raise AudioFormatError("esperado exatamente um fluxo de áudio")
        stream = container.streams.audio[0]
        ctx = stream.codec_context
        if ctx.name != "opus":
            raise AudioFormatError(f"codec {ctx.name!r}: esperado opus")
        if ctx.channels != 1:
            raise AudioFormatError(f"{ctx.channels} canais: esperado mono")
        total = 0
        peak = 0.0
        for frame in container.decode(stream):
            arr = frame.to_ndarray()
            total += arr.shape[-1]
            if arr.size:
                peak = max(peak, float(np.max(np.abs(arr.astype(np.float32)))))
        rate = int(ctx.sample_rate or OPUS_RATE)
        if total == 0:
            raise AudioFormatError("OGG sem amostras decodificáveis")
        scale = 32768.0 if arr.dtype.kind in "iu" else 1.0
        peak_db = 20 * math.log10(max(peak / scale, 1e-9))
        return AudioInfo("ogg", "opus", rate, 1, total / rate, peak_db)
    finally:
        container.close()
