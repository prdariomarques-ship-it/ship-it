#!/usr/bin/env python3
"""Valida os handlers do shim FlowCore contra a API real (localhost:8080).

Simula o ciclo completo do executor: constrói ToolContext mínimo e chama
cada handler, imprimindo o JSON retornado. O FlowCore precisa estar no ar
(`python3 flowcore.py serve`) — o health check do próprio FlowCore é
chamado primeiro para falhar cedo e com mensagem clara.
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.tools.base import ToolContext
from agents.tools import flowcore_tools as ft


async def main() -> int:
    # Context mínimo — handlers não tocam no DB, mas o contrato exige.
    context = ToolContext(db=None, user=None, contact_id=None)  # type: ignore[arg-type]

    results = {}
    for name, handler, args in [
        ("flowcore_health", ft.flowcore_health_tool.handler, {}),
        ("flowcore_macro_scores", ft.macro_scores_tool.handler, {}),
        ("flowcore_regime_signals", ft.regime_signals_tool.handler, {}),
        ("flowcore_observer_events", ft.observer_events_tool.handler, {}),
        ("flowcore_portfolio_list", ft.portfolio_list_tool.handler, {}),
        ("flowcore_portfolio_summary", ft.portfolio_summary_tool.handler, {"portfolio_id": "1"}),
        ("flowcore_portfolio_impact", ft.portfolio_impact_tool.handler, {"portfolio_id": "1"}),
    ]:
        raw = await handler(context, **args)
        # FlowCore API replies are plain JSON bodies (not envelopes) — the
        # shim returns them as-is. A healthy API response = valid JSON with
        # no "error" key at top level and no "FlowCore unavailable" prefix.
        unavailable = raw.startswith('{"error"') and "FlowCore unavailable" in raw
        try:
            parsed = json.loads(raw)
            valid_json = True
        except json.JSONDecodeError:
            parsed, valid_json = None, False
        top_error = isinstance(parsed, dict) and "error" in parsed
        status_ok = valid_json and not unavailable and not top_error
        print(f"[{'OK' if status_ok else 'FALHOU'}] {name}: {raw[:130].replace(chr(10), ' ')}")
        results[name] = status_ok

    failed = [k for k, ok_flag in results.items() if not ok_flag]
    if failed:
        print("falhou:", failed)
        return 1
    print("todos os handlers do shim responderam com ok=True")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
