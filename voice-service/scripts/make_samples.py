"""Gera as três amostras PRIVADAS (textos fictícios) pelo serviço em execução, para o proprietário ouvir.

As saídas vão para --out (fora do git; o diretório é criado 0700). Não envia nada a ninguém.
Uso: VOICE_URL=http://127.0.0.1:8765 VOICE_TOKEN=... python -m scripts.make_samples --out /caminho/privado
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

import httpx

from scripts.samples import SAMPLES


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", choices=sorted(SAMPLES), help="gera só esta amostra")
    ap.add_argument("--takes", type=int, default=1, help="quantas tomadas gerar de cada amostra (a geração é estocástica: tomadas diferem)")
    args = ap.parse_args(argv)
    if not 1 <= args.takes <= 10:
        print("--takes deve estar entre 1 e 10", file=sys.stderr)
        return 2
    url, token = os.environ.get("VOICE_URL", "http://127.0.0.1:8765"), os.environ.get("VOICE_TOKEN", "")
    if not token:
        print("defina VOICE_TOKEN no ambiente (não passe pela linha de comando)", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(args.out, 0o700)
    headers = {"Authorization": f"Bearer {token}"}
    manifest = []
    with httpx.Client(base_url=url, headers=headers, timeout=300) as c:
        todo = [(n, t, k) for n, t in SAMPLES.items() if args.only in (None, n) for k in range(1, args.takes + 1)]
        for name, text, take in todo:
            label = name if args.takes == 1 else f"{name}_t{take}"
            r = c.post("/v1/synthesize", json={"request_id": f"amostra-{label}-{uuid.uuid4().hex[:8]}", "text": text, "language": "pt"})
            r.raise_for_status()
            meta = r.json()
            audio = c.get(f"/v1/audio/{meta['audio_id']}")
            audio.raise_for_status()
            assert hashlib.sha256(audio.content).hexdigest() == meta["sha256"]
            target = args.out / f"{label}.ogg"
            target.write_bytes(audio.content)
            os.chmod(target, 0o600)
            c.delete(f"/v1/audio/{meta['audio_id']}")
            manifest.append({"amostra": label, "arquivo": target.name, "texto": text, "duracao_s": meta["duration_seconds"],
                             "sha256": meta["sha256"], "motor": meta["engine"], "revisao_modelo": meta["model_revision"],
                             "referencia_sha256": meta["reference_sha256"]})
    (args.out / "manifesto.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
