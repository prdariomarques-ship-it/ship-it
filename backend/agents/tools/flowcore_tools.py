"""FlowCore market-intelligence tools — REST shim into the FlowCore API.

Every handler is a thin HTTP pass-through to FlowCore's REST surface
(`/api/macro-score/*`, `/api/regime/*`, `/api/observer/*`,
`/api/portfolios/*`), with a small retry/backoff layer shared with the
rest of the Dario OS (same contract as whatsapp_request_*). The LLM
never touches a database or an engine directly; it only consumes the
deterministic outputs the FlowCore API already exposes.

Tools self-register via `Tool.__post_init__` (import is enough) and are
wired into the `personal` agent in `backend/agents/personal_agent.py`.

Requires the FlowCore API to be reachable at `flowcore_base_url`
(default `http://localhost:8080`). When the API is down, handlers return
a structured JSON error so the model degrades gracefully instead of
hallucinating market data.
"""
from __future__ import annotations

import asyncio
import json

import httpx

from agents.tools.base import Tool, ToolContext, ok
from utils.config import get_settings


def _base_url() -> str:
    """FlowCore API address — configurable, defaults to localhost."""
    return getattr(get_settings(), "flowcore_base_url", "http://localhost:8080")


async def _flowcore_get(path: str, timeout: float = 20.0) -> str:
    """GET with exponential backoff, same contract as the WhatsApp
    provider (PROD-001: resilience to transient provider failures)."""
    settings = get_settings()
    max_attempts = getattr(settings, "flowcore_request_max_attempts", 3)
    backoff = getattr(settings, "flowcore_request_backoff_seconds", 1.0)
    url = f"{_base_url().rstrip('/')}{path}"
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
            if response.status_code == 200:
                return response.text
            last_error = RuntimeError(
                f"FlowCore API HTTP {response.status_code}: {response.text[:200]}"
            )
            if response.status_code < 500:
                break  # client error — retry won't help
        except httpx.HTTPError as exc:
            last_error = exc
        await asyncio.sleep(backoff * (2 ** attempt))
    return json.dumps({"error": f"FlowCore unavailable: {last_error}"})


async def _macro_scores(context: ToolContext) -> str:
    return await _flowcore_get("/api/macro-score/scores")


async def _regime_signals(context: ToolContext) -> str:
    return await _flowcore_get("/api/regime/signals")


async def _observer_events(context: ToolContext) -> str:
    return await _flowcore_get("/api/observer/events")


async def _observer_health(context: ToolContext) -> str:
    return await _flowcore_get("/api/observer/health")


async def _portfolio_list(context: ToolContext) -> str:
    return await _flowcore_get("/api/portfolios")


async def _portfolio_summary(context: ToolContext, portfolio_id: str) -> str:
    return await _flowcore_get(f"/api/portfolios/{portfolio_id}/summary")


async def _portfolio_impact(context: ToolContext, portfolio_id: str) -> str:
    return await _flowcore_get(f"/api/portfolios/{portfolio_id}/impact")


async def _flowcore_health(context: ToolContext) -> str:
    return await _flowcore_get("/api/health")


macro_scores_tool = Tool(
    name="flowcore_macro_scores",
    description=(
        "Scores determinísticos do Macro Score Engine do FlowCore — uma nota por "
        "dimensão macro (bolsas, crédito, dólar, inflação, commodities, juros...). "
        "Sem LLM, sem interpretação: números e status de dados."
    ),
    handler=_macro_scores,
)

regime_signals_tool = Tool(
    name="flowcore_regime_signals",
    description=(
        "Classificação de regime do Regime Engine do FlowCore (risk-on / risk-off / "
        "neutro) por dimensão, com thresholds determinísticos."
    ),
    handler=_regime_signals,
)

observer_events_tool = Tool(
    name="flowcore_observer_events",
    description=(
        "Últimos MarketEvents normalizados coletados pelo Observer Framework "
        "do FlowCore (cotações, notícias de mercado, fluxos). Dados brutos, sem "
        "interpretação."
    ),
    handler=_observer_events,
)

observer_health_tool = Tool(
    name="flowcore_observer_health",
    description=(
        "Saúde de cada fonte de dados do Observer Framework do FlowCore (última "
        "coleta, falhas, latência). Útil para diagnosticar por que um dado de "
        "mercado está desatualizado."
    ),
    handler=_observer_health,
)

portfolio_list_tool = Tool(
    name="flowcore_portfolio_list",
    description="Lista todos os portfólios registrados no FlowCore.",
    handler=_portfolio_list,
)

portfolio_summary_tool = Tool(
    name="flowcore_portfolio_summary",
    description=(
        "Resumo de um portfólio no FlowCore: holdings, valuation ao vivo e "
        "performance por holding."
    ),
    handler=_portfolio_summary,
    parameters={
        "type": "object",
        "properties": {
            "portfolio_id": {"type": "string", "description": "ID do portfólio, ex: 'demo'"},
        },
        "required": ["portfolio_id"],
    },
)

portfolio_impact_tool = Tool(
    name="flowcore_portfolio_impact",
    description=(
        "Impacto do regime macro atual sobre um portfólio no FlowCore: classificação "
        "ponderada das exposições vs. regime e recomendações determinísticas."
    ),
    handler=_portfolio_impact,
    parameters={
        "type": "object",
        "properties": {
            "portfolio_id": {"type": "string", "description": "ID do portfólio, ex: 'demo'"},
        },
        "required": ["portfolio_id"],
    },
)

flowcore_health_tool = Tool(
    name="flowcore_health",
    description=(
        "Health check rápido da API do FlowCore — verifica se o motor de "
        "inteligência de mercado está no ar e respondendo."
    ),
    handler=_flowcore_health,
)
