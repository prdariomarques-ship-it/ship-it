#!/usr/bin/env python3
"""Operador dos acompanhamentos comerciais da loja. NÃO é uma rotina agendada: só roda quando alguém o executa.

  python scripts/store_followups.py plan                 # simulação: o que seria agendado (nada é gravado)
  python scripts/store_followups.py run                  # simulação: o que seria enviado agora (nada é gravado/enviado)
  python scripts/store_followups.py plan --apply         # grava os agendamentos (exige STORE_FOLLOWUPS_ENABLED=true)
  python scripts/store_followups.py run  --apply         # coloca os envios na fila existente (exige STORE_FOLLOWUPS_ENABLED=true)
  python scripts/store_followups.py reconcile            # fecha o ciclo dos 'queued' e linhas de voz presas; nunca reenvia

A saída traz referências (ids, motivos, textos gerados a partir de fatos verificáveis); nunca imprime credenciais.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.session import async_session_factory  # noqa: E402
from services import store_followups, store_voice  # noqa: E402


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["plan", "run", "reconcile"])
    ap.add_argument("--apply", action="store_true", help="grava/enfileira de verdade (padrão: simulação)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    async with async_session_factory() as db:
        try:
            out: object
            if args.command == "plan":
                out = {"quote_resume": await store_followups.plan_quote_resumes(db, apply=args.apply),
                       "restock": await store_followups.plan_restocks(db, apply=args.apply)}
            elif args.command == "run":
                out = await store_followups.run_due(db, apply=args.apply, limit=args.limit)
            else:
                out = {"followups": await store_followups.reconcile(db), "voice": await store_voice.reconcile_stuck(db)}
        except store_followups.FollowupsDisabled as exc:
            print(f"recusado: {exc}", file=sys.stderr)
            return 2
    print(json.dumps({"apply": args.apply, "result": out}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
