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

from scripts.measure import SAMPLES


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    url, token = os.environ.get("VOICE_URL", "http://127.0.0.1:8765"), os.environ.get("VOICE_TOKEN", "")
    if not token:
        print("defina VOICE_TOKEN no ambiente (não passe pela linha de comando)", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(args.out, 0o700)
    headers = {"Authorization": f"Bearer {token}"}
    manifest = []
    with httpx.Client(base_url=url, headers=headers, timeout=300) as c:
        for name, text in SAMPLES.items():
            r = c.post("/v1/synthesize", json={"request_id": f"amostra-{name}-{uuid.uuid4().hex[:8]}", "text": text, "language": "pt"})
            r.raise_for_status()
            meta = r.json()
            audio = c.get(f"/v1/audio/{meta['audio_id']}")
            audio.raise_for_status()
            assert hashlib.sha256(audio.content).hexdigest() == meta["sha256"]
            target = args.out / f"{name}.ogg"
            target.write_bytes(audio.content)
            os.chmod(target, 0o600)
            c.delete(f"/v1/audio/{meta['audio_id']}")
            manifest.append({"amostra": name, "arquivo": target.name, "texto": text, "duracao_s": meta["duration_seconds"],
                             "sha256": meta["sha256"], "motor": meta["engine"], "revisao_modelo": meta["model_revision"],
                             "referencia_sha256": meta["reference_sha256"]})
    (args.out / "manifesto.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
