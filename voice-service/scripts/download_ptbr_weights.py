#!/usr/bin/env python3
"""Monta a pasta de pesos do motor `chatterbox_ptbr` e imprime o VOICE_MODEL_REVISION a registrar.

O pacote pt-BR usa dois repositórios no Hugging Face (ver `chatterbox/src/chatterbox/tts.py` do Space): o base (`ve.pt`, tokenizador,
`conds.pt`) e o pt-BR (`t3_pt_br.safetensors`, `s3gen_v3.pt`). Os nomes de arquivo são lidos do PRÓPRIO código do Space (pasta
informada em --space-dir), para não divergirem. Cada repositório é baixado numa revisão (commit) fixa; sem --*-revision, resolve a atual e
imprime. Depois disso o serviço roda offline.

  python scripts/download_ptbr_weights.py --space-dir C:\\voz\\space_ptbr --dest C:\\models\\chatterbox_ptbr [--base-revision <commit>] [--ptbr-revision <commit>]

Roda no ambiente do pacote pt-BR (`.venv-ptbr`) e precisa de acesso a huggingface.co. Confira a licença nos cartões dos dois modelos
antes de uso comercial.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

BASE_REPO_ID = "ResembleAI/chatterbox"
PTBR_REPO_ID = "ResembleAI/Chatterbox-Multilingual-pt-br"
SHORT = 12  # a revisão registrada no backend cabe em 64 caracteres: usa os 12 primeiros do commit de cada repositório


def short_revision(base_sha: str, ptbr_sha: str) -> str:
    return f"base-{base_sha[:SHORT]}+ptbr-{ptbr_sha[:SHORT]}"


def read_filenames(space_dir: Path) -> dict[str, str]:
    """Nomes de arquivo exigidos, lidos do código do Space (não copiados para cá)."""
    src = Path(space_dir) / "chatterbox" / "src"
    if not (src / "chatterbox" / "tts.py").is_file():
        raise SystemExit(f"não achei {src / 'chatterbox' / 'tts.py'}: --space-dir deve ser a pasta do Space baixado")
    sys.path.insert(0, str(src))
    try:
        tts = importlib.import_module("chatterbox.tts")
    finally:
        sys.path.remove(str(src))
    return {"tokenizer": tts.TOKENIZER_FILENAME, "t3": tts.T3_FILENAME, "s3gen": tts.S3GEN_FILENAME}


def plan(names: dict[str, str], dest: str, base_rev: str, ptbr_rev: str) -> list[dict]:
    """Chamadas de snapshot_download (separadas para serem testáveis sem rede)."""
    return [
        {"repo_id": BASE_REPO_ID, "repo_type": "model", "local_dir": dest, "revision": base_rev,
         "allow_patterns": ["ve.pt", names["tokenizer"], "conds.pt"]},
        {"repo_id": PTBR_REPO_ID, "repo_type": "model", "local_dir": dest, "revision": ptbr_rev,
         "allow_patterns": [names["t3"], names["s3gen"]]},
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--space-dir", type=Path, required=True)
    ap.add_argument("--dest", required=True, help="pasta de destino (será VOICE_MODEL_DIR)")
    ap.add_argument("--base-revision")
    ap.add_argument("--ptbr-revision")
    ns = ap.parse_args(argv)
    names = read_filenames(ns.space_dir)
    from huggingface_hub import HfApi, snapshot_download

    api = HfApi()
    base_rev = ns.base_revision or api.model_info(BASE_REPO_ID).sha
    ptbr_rev = ns.ptbr_revision or api.model_info(PTBR_REPO_ID).sha
    for call in plan(names, ns.dest, base_rev, ptbr_rev):
        snapshot_download(**call)
    print(
        f"\nPesos em: {ns.dest}\nVOICE_MODEL_DIR={ns.dest}\nVOICE_MODEL_REVISION={short_revision(base_rev, ptbr_rev)}\n"
        f"commits completos: {BASE_REPO_ID}@{base_rev} | {PTBR_REPO_ID}@{ptbr_rev}\n"
        "Confira a licença nos cartões dos dois modelos antes de usar comercialmente."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
