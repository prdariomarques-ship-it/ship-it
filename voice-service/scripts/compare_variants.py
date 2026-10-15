"""Teste às cegas de variações do Chatterbox, direto no PC do titular (sem subir o serviço).

Gera as 3 frases fictícias de `scripts.measure.SAMPLES` com a SUA gravação de referência em várias combinações de `cfg_weight`/`exaggeration`,
grava arquivos A_*.wav, B_*.wav... numa pasta privada e guarda a chave (qual letra é qual variação) em `chave.json`. Ouça primeiro, abra a chave depois.
Nada é enviado a ninguém; a gravação de referência não sai do PC.

Uso (PowerShell, dentro de voice-service, com o ambiente do Chatterbox ativo):
  python -m scripts.compare_variants --reference "C:\\caminho\\gravacao.wav" --out C:\\voz\\teste_cego
  # pesos locais (opcional; sem isso baixa/usa o cache do Hugging Face):  --model-dir C:\\models\\chatterbox
  # variações próprias:  --variant cfg=0.5,exg=0.5 --variant cfg=0,exg=0.5
Referência: .wav mono, ~10-15 s limpos, em PORTUGUÊS (o idioma da referência deve ser o do texto, senão o sotaque vaza).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import wave
from pathlib import Path

import numpy as np

from scripts.measure import SAMPLES

DEFAULT_VARIANTS = ("cfg=0.5,exg=0.5", "cfg=0,exg=0.5", "cfg=0.3,exg=0.7")


def parse_variant(spec: str) -> dict[str, float]:
    values = {"cfg": 0.5, "exg": 0.5}
    for part in spec.split(","):
        key, _, raw = part.strip().partition("=")
        if key not in values or not raw:
            raise ValueError(f"variação inválida {spec!r}: use cfg=<0..1>,exg=<0..2>")
        values[key] = float(raw)
    if not 0.0 <= values["cfg"] <= 1.0:
        raise ValueError("cfg deve estar entre 0 e 1")
    if not 0.0 <= values["exg"] <= 2.0:
        raise ValueError("exg deve estar entre 0 e 2")
    return values


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    clipped = np.clip(np.asarray(samples, dtype=np.float32).reshape(-1), -1.0, 1.0)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes((clipped * 32767.0).astype("<i2").tobytes())


def load_model(model_dir: Path | None, device: str):
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # type: ignore

    if model_dir is not None:
        return ChatterboxMultilingualTTS.from_local(model_dir, device)
    return ChatterboxMultilingualTTS.from_pretrained(device=device)


def main(argv: list[str] | None = None, model_factory=load_model) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reference", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model-dir", type=Path, default=None)
    ap.add_argument("--device", default=None)
    ap.add_argument("--language", default="pt")
    ap.add_argument("--variant", action="append", default=None)
    ap.add_argument("--seed", type=int, default=None, help="semente do sorteio das letras (padrão: aleatória)")
    args = ap.parse_args(argv)
    if not args.reference.is_file():
        print(f"gravação de referência não encontrada: {args.reference}")
        return 2
    variants = [parse_variant(v) for v in (args.variant or DEFAULT_VARIANTS)]
    device = args.device
    if device is None:
        import torch  # type: ignore

        device = "cuda" if torch.cuda.is_available() else "cpu"
    args.out.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(args.out, 0o700)
    except OSError:
        pass
    model = model_factory(args.model_dir, device)
    letters = [chr(ord("A") + i) for i in range(len(variants))]
    order = list(range(len(variants)))
    random.Random(args.seed).shuffle(order)
    key: dict[str, dict[str, float]] = {}
    for letter, index in zip(letters, order):
        var = variants[index]
        key[letter] = var
        for name, text in SAMPLES.items():
            wav = model.generate(text, language_id=args.language, audio_prompt_path=str(args.reference), exaggeration=var["exg"], cfg_weight=var["cfg"])
            samples = wav.squeeze().detach().cpu().numpy()
            write_wav(args.out / f"{letter}_{name}.wav", samples, int(model.sr))
            print(f"gerado {letter}_{name}.wav")
    (args.out / "chave.json").write_text(json.dumps({"idioma": args.language, "modelo_local": str(args.model_dir) if args.model_dir else "cache/HF", "variacoes": key}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nPronto. Ouça os arquivos de {args.out} SEM abrir chave.json; depois me diga a letra preferida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
