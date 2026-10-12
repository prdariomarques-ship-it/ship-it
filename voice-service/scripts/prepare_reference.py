"""Prepara o perfil de voz de um agente a partir da gravação de referência — SEM filtros e SEM alterar o original.

- O arquivo original é copiado intacto para `<perfil>/original/` com o seu SHA-256 (preservação).
- `reference.wav` é o trecho [--start, --end] do original: só recorte e mistura para mono. Reamostragem só com --resample
  explícito. Nenhuma normalização, redução de ruído, equalização ou compressão.
- O perfil só é criado com consentimento declarado (--voice-owner, --consent-scope, --confirm-authorized).

Uso: python scripts/prepare_reference.py ORIGINAL --profiles-dir DIR --agent loja --start 3.0 --end 15.0 \\
        --voice-owner "NOME" --consent-scope "TEXTO" --confirm-authorized [--reference-text "transcrição exata do trecho"]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import wave
from pathlib import Path

import numpy as np

from scripts.analyze_reference import load_mono


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_wav16(path: Path, x: np.ndarray, sr: int) -> None:
    pcm = np.clip(np.round(x * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("original", type=Path)
    ap.add_argument("--profiles-dir", type=Path, required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--resample", type=int, default=None, help="taxa alvo (Hz); omitido = mantém a original")
    ap.add_argument("--reference-text", default=None)
    ap.add_argument("--voice-owner", required=True)
    ap.add_argument("--consent-scope", required=True)
    ap.add_argument("--confirm-authorized", action="store_true")
    ap.add_argument("--display-name", default=None)
    args = ap.parse_args(argv)

    if not args.confirm_authorized:
        print("recusado: use --confirm-authorized somente se o titular da voz autorizou este uso", file=sys.stderr)
        return 2
    if not (0 <= args.start < args.end):
        print("intervalo inválido", file=sys.stderr)
        return 2
    x, sr, _ = load_mono(args.original)
    seg = x[int(args.start * sr): int(args.end * sr)]
    if len(seg) < sr * 3:
        print("trecho com menos de 3 s", file=sys.stderr)
        return 2
    if args.resample and args.resample != sr:
        import av
        resampler = av.AudioResampler(format="flt", layout="mono", rate=args.resample)
        frame = av.AudioFrame.from_ndarray(seg.reshape(1, -1).astype(np.float32), format="flt", layout="mono")
        frame.sample_rate = sr
        out = [f.to_ndarray().reshape(-1) for f in resampler.resample(frame)] + \
              [f.to_ndarray().reshape(-1) for f in (resampler.resample(None) or [])]
        seg, sr = np.concatenate(out), args.resample

    profile_dir = args.profiles_dir / args.agent
    if profile_dir.exists():
        print(f"recusado: {profile_dir} já existe (não sobrescrevo perfis)", file=sys.stderr)
        return 2
    (profile_dir / "original").mkdir(parents=True)
    original_copy = profile_dir / "original" / args.original.name
    shutil.copy2(args.original, original_copy)
    ref = profile_dir / "reference.wav"
    write_wav16(ref, seg, sr)
    meta = {
        "agent": args.agent, "display_name": args.display_name or f"Voz autorizada ({args.agent})", "language": "pt",
        "reference_file": "reference.wav", "reference_sha256": sha256_file(ref), "reference_text": args.reference_text,
        "source": {"file": args.original.name, "sha256": sha256_file(original_copy), "start_seconds": args.start,
                   "end_seconds": args.end, "processing": "recorte + mono" + (f" + reamostragem {args.resample} Hz" if args.resample else "")},
        "consent": {"authorized": True, "voice_owner": args.voice_owner, "scope": args.consent_scope},
    }
    (profile_dir / "profile.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"perfil": str(profile_dir), "reference_sha256": meta["reference_sha256"], "original_sha256": meta["source"]["sha256"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
