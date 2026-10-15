"""Somente leitura: lista os arquivos, tamanhos, licença declarada e o início do cartão (README) de um repositório do Hugging Face, SEM baixar pesos.

Serve para conferir o pacote pt-BR do Chatterbox e a licença dos pesos antes de adaptar o motor.
Uso: python -m scripts.inspect_hf_repo ResembleAI/Chatterbox-Multilingual-pt-br [outro/repositorio ...]
Precisa de internet com acesso a huggingface.co (o ambiente de desenvolvimento não tem). Não envia nada a ninguém.
"""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    repos = list(argv if argv is not None else sys.argv[1:])
    if not repos:
        print(__doc__)
        return 2
    from huggingface_hub import HfApi, hf_hub_download  # pip install huggingface_hub

    api = HfApi()
    for repo in repos:
        print("=" * 78, f"\nREPOSITÓRIO: {repo}")
        try:
            info = api.model_info(repo, files_metadata=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  não consegui abrir: {type(exc).__name__}: {exc}")
            continue
        print(f"  revisão (commit): {info.sha}")
        print(f"  última alteração: {info.last_modified}")
        print(f"  gated: {info.gated}")
        card = info.card_data
        print(f"  licença declarada: {getattr(card, 'license', None)}  | nome da licença: {getattr(card, 'license_name', None)}  | link: {getattr(card, 'license_link', None)}")
        print(f"  idiomas: {getattr(card, 'language', None)}  | tags: {', '.join((info.tags or [])[:12])}")
        print("  arquivos (tamanho em MB):")
        for f in sorted(info.siblings or [], key=lambda s: s.rfilename):
            size = f"{(f.size or 0) / 1e6:9.1f}" if f.size is not None else "      ?"
            print(f"    {size}  {f.rfilename}")
        try:
            readme = hf_hub_download(repo, "README.md", revision=info.sha)
            with open(readme, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
            print("  --- início do cartão (80 linhas) ---")
            print("\n".join("  | " + line for line in lines[:80]))
        except Exception as exc:  # noqa: BLE001
            print(f"  cartão não lido: {type(exc).__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
