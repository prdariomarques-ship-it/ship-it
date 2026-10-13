#!/usr/bin/env python3
"""Baixa os pesos do Chatterbox Multilingual para uma pasta local e imprime a REVISÃO (commit) a fixar em VOICE_MODEL_REVISION.

Roda no computador que vai hospedar o voice-service (precisa de acesso a huggingface.co). Depois do download o serviço roda
offline (HF_HUB_OFFLINE=1). Arquivos exigidos por `ChatterboxMultilingualTTS.from_local` (código-fonte upstream, chatterbox-tts
0.1.7): ve.pt, t3_mtl23ls_v2.safetensors, s3gen.pt, grapheme_mtl_merged_expanded_v1.json (+ conds.pt opcional).

  python scripts/download_weights.py --dest C:\\models\\chatterbox [--revision <commit>]
"""
from __future__ import annotations

import argparse

REPO_ID = "ResembleAI/chatterbox"
FILES = ["ve.pt", "t3_mtl23ls_v2.safetensors", "s3gen.pt", "grapheme_mtl_merged_expanded_v1.json", "conds.pt"]


def build_args(dest: str, revision: str | None) -> dict:
    """Argumentos de snapshot_download (separado para ser testável sem rede)."""
    args: dict = {"repo_id": REPO_ID, "repo_type": "model", "local_dir": dest, "allow_patterns": FILES}
    if revision:
        args["revision"] = revision
    return args


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", required=True, help="pasta de destino (será VOICE_MODEL_DIR)")
    ap.add_argument("--revision", help="commit a baixar; se omitido, resolve o atual e IMPRIME para você fixar")
    ns = ap.parse_args()
    from huggingface_hub import HfApi, snapshot_download

    revision = ns.revision or HfApi().model_info(REPO_ID).sha
    snapshot_download(**build_args(ns.dest, revision))
    print(f"\nPesos em: {ns.dest}\nVOICE_MODEL_REVISION={revision}\nConfira a licença no cartão do modelo antes de usar comercialmente:\n  https://huggingface.co/{REPO_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
