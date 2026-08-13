"""Mercado (market intelligence) endpoints — read-only proxy over FlowCore.

Mirrors the resilience contract of the FlowCore agent tools
(`backend/agents/tools/flowcore_tools.py`): every endpoint degrades to a
structured JSON answer instead of crashing when the FlowCore API is
unreachable or slow. The LLM, the dashboard UI and the mobile clients
consume the same deterministic outputs FlowCore already computes.

Read-only by construction: only GET routes; no credentials are forwarded,
only bearer-free public endpoints of FlowCore are proxied.
"""
from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter

from utils.config import get_settings

router = APIRouter(prefix="/mercado", tags=["mercado"])

_TIMEOUT = 25.0  # seconds; FlowCore compute (yfinance/z-scores) is local and fast
_MAX_ATTEMPTS = 2


def _base_url() -> str:
    return getattr(get_settings(), "flowcore_base_url", "http://localhost:8080")


def _unavailable(detail: str) -> dict:
    return {
        "available": False,
        "error": "FlowCore API indisponivel",
        "detail": detail,
    }


async def _proxy(path: str, default: dict) -> dict:
    """GET `path` on FlowCore with retry/backoff; structured error on failure."""
    settings = get_settings()
    max_attempts = getattr(settings, "flowcore_request_max_attempts", _MAX_ATTEMPTS)
    backoff = getattr(settings, "flowcore_request_backoff_seconds", 0.5)
    url = f"{_base_url().rstrip('/')}{path}"
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(url)
            if response.status_code == 200:
                return response.json()
            last_error = RuntimeError(
                f"HTTP {response.status_code}: {response.text[:200]}"
            )
            if response.status_code < 500:
                break  # client error — retry will not help
        except httpx.HTTPError as exc:
            last_error = exc
        await asyncio.sleep(backoff * (2 ** attempt))
    default.update(_unavailable(str(last_error)))
    return default


@router.get("/scores")
async def mercado_scores() -> dict:
    """Macro-score dimensions (commodities, liquidity, risk sentiment)."""
    return await _proxy("/api/macro-score/scores", {"scores": []})


@router.get("/events")
async def mercado_events() -> dict:
    """Recent market events from the observers (yfinance-backed)."""
    return await _proxy("/api/observer/events", {"events": []})


@router.get("/regime")
async def mercado_regime() -> dict:
    """Current market regime classification (deterministic z-score
    threshold rules — same no-network, no-502 property as the other
    routes). FlowCore exposes it at /api/regime/signals (Sprint 20)."""
    return await _proxy("/api/regime/signals", {"signals": None})


@router.get("/health")
async def mercado_health() -> dict:
    """Combined health: Dario OS backend + FlowCore reachability."""
    flowcore_ok = False
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(f"{_base_url().rstrip('/')}/api/health")
        flowcore_ok = response.status_code == 200
    except Exception:
        flowcore_ok = False
    return {"backend": "ok", "flowcore": flowcore_ok, "flowcore_url": _base_url()}
