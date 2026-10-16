"""Teste às cegas de variações do Chatterbox, direto no PC do titular (sem subir o serviço).

Gera as 3 frases fictícias de `scripts.measure.SAMPLES` com a SUA gravação de referência em várias combinações de `cfg_weight`/`exaggeration`,
grava arquivos A_*.wav, B_*.wav... numa pasta privada e guarda a chave (qual letra é qual variação) em `chave.json`. Ouça primeiro, abra a chave depois.
Nada é enviado a ninguém; a gravação de referência não sai do PC.

Uso (PowerShell, dentro de voice-service, com o ambiente do Chatterbox ativo):
  python -m scripts.compare_variants --reference "C:\\caminho\\gravacao.wav" --out C:\\voz\\teste_cego
  # pesos locais (opcional; sem isso baixa/usa o cache do Hugging Face):  --model-dir C:\\models\\chatterbox
  # variações próprias:  --variant cfg=0.5,exg=0.5 --variant cfg=0,exg=0.5,temp=0.6,rep=1.4
  # só um trecho da referência (WAV, sem filtro):  --start 7 --end 19
  # pacote pt-BR oficial (código do Space da Resemble, ambiente separado):  --space-dir C:\\voz\\space_ptbr
    (esse motor só aceita cfg, exg e temp; o código do Space não tem rep/minp/topp nem o detector de repetição que corta a fala)
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

from scripts.samples import SAMPLES

DEFAULT_VARIANTS = ("cfg=0.5,exg=0.5", "cfg=0,exg=0.5", "cfg=0.3,exg=0.7")


# chave -> (parametro do generate(), padrao do Chatterbox, minimo, maximo)
_PARAMS = {
    "cfg": ("cfg_weight", 0.5, 0.0, 1.0),
    "exg": ("exaggeration", 0.5, 0.0, 2.0),
    "temp": ("temperature", 0.8, 0.05, 5.0),
    "rep": ("repetition_penalty", 1.2, 1.0, 3.0),
    "minp": ("min_p", 0.05, 0.0, 1.0),
    "topp": ("top_p", 1.0, 0.0, 1.0),
}


def parse_variant(spec: str) -> dict[str, float]:
    """`cfg=0,exg=0.5,temp=0.6`: so as chaves informadas mudam; as demais ficam no padrao do Chatterbox."""
    values = {key: default for key, (_, default, _, _) in _PARAMS.items()}
    for part in spec.split(","):
        key, _, raw = part.strip().partition("=")
        if key not in values or not raw:
            raise ValueError(f"variação inválida {spec!r}: chaves aceitas: {', '.join(_PARAMS)}")
        values[key] = float(raw)
    for key, (_, _, low, high) in _PARAMS.items():
        if not low <= values[key] <= high:
            raise ValueError(f"{key} deve estar entre {low} e {high}")
    return values


def trim_wav(source: Path, destination: Path, start: float, end: float) -> Path:
    """Recorta [start, end] s de um WAV PCM, SEM filtro, ganho ou normalizacao (so copia as amostras do trecho)."""
    with wave.open(str(source), "rb") as reader:
        rate, width, channels = reader.getframerate(), reader.getsampwidth(), reader.getnchannels()
        total = reader.getnframes()
        first = max(0, min(total, int(start * rate)))
        last = max(first, min(total, int(end * rate)))
        reader.setpos(first)
        frames = reader.readframes(last - first)
    if last - first < rate:
        raise ValueError("o trecho recortado tem menos de 1 segundo")
    with wave.open(str(destination), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(frames)
    return destination


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


# O generate() do Space pt-BR só aceita estes parametros (sem repetition_penalty/min_p/top_p).
PTBR_PARAMS = ("cfg", "exg", "temp")


def load_ptbr_model(space_dir: Path, device: str):
    """Carrega o pacote pt-BR com o código-fonte do próprio Space (pasta baixada com `snapshot_download(repo_type="space")`)."""
    import sys

    src = Path(space_dir) / "chatterbox" / "src"
    if not (src / "chatterbox" / "tts.py").is_file():
        raise FileNotFoundError(f"não achei {src / 'chatterbox' / 'tts.py'}: baixe o Space antes (ver docs/EXECUTAR_NO_PC_RTX3060.md)")
    sys.path.insert(0, str(src))
    from chatterbox.tts import ChatterboxTTS  # type: ignore  # o 'chatterbox' do Space, não o do PyPI

    return ChatterboxTTS.from_pretrained(device)


def main(argv: list[str] | None = None, model_factory=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reference", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model-dir", type=Path, default=None)
    ap.add_argument("--space-dir", type=Path, default=None, help="usa o pacote pt-BR com o código do Space baixado nesta pasta")
    ap.add_argument("--device", default=None)
    ap.add_argument("--language", default="pt")
    ap.add_argument("--variant", action="append", default=None)
    ap.add_argument("--seed", type=int, default=None, help="semente do sorteio das letras (padrão: aleatória)")
    ap.add_argument("--start", type=float, default=None, help="início (s) do trecho da referência a usar (só WAV; sem filtro)")
    ap.add_argument("--end", type=float, default=None, help="fim (s) do trecho da referência a usar")
    args = ap.parse_args(argv)
    if not args.reference.is_file():
        print(f"gravação de referência não encontrada: {args.reference}")
        return 2
    variants = [parse_variant(v) for v in (args.variant or DEFAULT_VARIANTS)]
    ptbr = args.space_dir is not None
    if ptbr:
        for spec in args.variant or ():
            extra = [k.strip().partition("=")[0] for k in spec.split(",") if k.strip().partition("=")[0] not in PTBR_PARAMS]
            if extra:
                print(f"o motor pt-BR do Space não aceita {', '.join(extra)}; use só {', '.join(PTBR_PARAMS)}")
                return 2
    if model_factory is None:
        model_factory = (lambda _d, dev: load_ptbr_model(args.space_dir, dev)) if ptbr else load_model
    used = {k: v for k, v in _PARAMS.items() if not ptbr or k in PTBR_PARAMS}
    reference = args.reference
    if (args.start is None) != (args.end is None):
        print("use --start e --end juntos")
        return 2
    device = args.device
    if device is None:
        import torch  # type: ignore

        device = "cuda" if torch.cuda.is_available() else "cpu"
    args.out.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(args.out, 0o700)
    except OSError:
        pass
    if args.start is not None:
        reference = trim_wav(args.reference, args.out / "referencia_recortada.wav", args.start, args.end)
        print(f"referência recortada: {args.start:.1f}–{args.end:.1f} s -> {reference}")
    model = model_factory(args.model_dir, device)
    letters = [chr(ord("A") + i) for i in range(len(variants))]
    order = list(range(len(variants)))
    random.Random(args.seed).shuffle(order)
    key: dict[str, dict[str, float]] = {}
    for letter, index in zip(letters, order):
        var = variants[index]
        key[letter] = var
        for name, text in SAMPLES.items():
            wav = model.generate(
                text, language_id=args.language, audio_prompt_path=str(reference),
                **{param: var[key] for key, (param, _, _, _) in used.items()},
            )
            samples = wav.squeeze().detach().cpu().numpy()
            write_wav(args.out / f"{letter}_{name}.wav", samples, int(model.sr))
            print(f"gerado {letter}_{name}.wav")
    (args.out / "chave.json").write_text(json.dumps({"idioma": args.language, "modelo_local": str(args.space_dir) if ptbr else (str(args.model_dir) if args.model_dir else "cache/HF"), "motor": "ptbr-space" if ptbr else "v2-pypi", "variacoes": key}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nPronto. Ouça os arquivos de {args.out} SEM abrir chave.json; depois me diga a letra preferida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
