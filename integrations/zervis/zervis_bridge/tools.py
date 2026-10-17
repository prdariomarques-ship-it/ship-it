"""Servidor MCP: ferramentas somente-leitura sobre o Dario OS.

Cada ferramenta mapeia um caminho do allowlist de `auth/scopes.py` (ADR-0003)
ou o buffer de eventos sanitizado. Falhas viram `{"error": ...}` (como o shim
FlowCore) para o modelo degradar sem inventar dados.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field

from .buffer import EventBuffer
from .client import DarioOSClient, DarioOSError
from .subscriber import EventSubscriber

_INSTRUCTIONS = (
    "Leitura do estado do Dario OS (somente leitura). Os dados são do dono da "
    "instância; não repita telefones, e-mails ou conteúdo de mensagens."
)

Limit = Annotated[int, Field(ge=1, le=100)]


def build_server(
    client: DarioOSClient,
    buffer: EventBuffer,
    subscriber: EventSubscriber,
    allowed_hosts: list[str],
) -> FastMCP:
    mcp = FastMCP(
        "darioos",
        instructions=_INSTRUCTIONS,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts
        ),
    )

    async def _safe(call: Callable[[], Awaitable[Any]]) -> Any:
        try:
            return await call()
        except DarioOSError as exc:
            return {"error": str(exc)}

    @mcp.tool(name="darioos_status")
    async def status() -> Any:
        """Saúde dos componentes do Dario OS (API, banco, Redis, WhatsApp...) e da ponte."""
        components = await _safe(lambda: client.get("/admin/status"))
        return {
            "components": components,
            "bridge": {
                "redis_events_connected": subscriber.connected,
                "latest_event_seq": buffer.latest_seq,
                "events_dropped": subscriber.dropped,
            },
        }

    @mcp.tool(name="darioos_agents")
    async def agents() -> Any:
        """Agentes registrados e suas ferramentas."""
        return await _safe(lambda: client.get("/admin/agents"))

    @mcp.tool(name="darioos_executions")
    async def executions(
        period: Annotated[str, Field(pattern="^(today|24h|7d|30d)$")] = "24h",
        agent: str | None = None,
        limit: Limit = 20,
    ) -> Any:
        """Linha do tempo recente de execuções (jobs e eventos de agentes)."""
        params: dict[str, Any] = {"period": period, "limit": limit}
        if agent:
            params["agent"] = agent[:60]
        return await _safe(lambda: client.get("/admin/executions", params))

    @mcp.tool(name="darioos_context")
    async def context() -> Any:
        """Contexto atual observado do dono (agenda, metas, pendências)."""
        return await _safe(lambda: client.get("/admin/observation"))

    @mcp.tool(name="darioos_goals")
    async def goals(
        status: Annotated[str | None, Field(pattern="^[a-z_]{1,30}$")] = None,
        limit: Limit = 20,
    ) -> Any:
        """Metas do dono; `status` opcional (ex.: active)."""
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return await _safe(lambda: client.get("/goals", params))

    @mcp.tool(name="darioos_goals_ready")
    async def goals_ready() -> Any:
        """Metas prontas para avançar (sem dependências abertas)."""
        return await _safe(lambda: client.get("/goals/ready"))

    @mcp.tool(name="darioos_tasks")
    async def tasks() -> Any:
        """Tarefas do dono."""
        return await _safe(lambda: client.get("/tasks"))

    @mcp.tool(name="darioos_recent_events")
    async def recent_events(
        since: Annotated[int, Field(ge=0)] = 0, limit: Limit = 50
    ) -> Any:
        """Eventos do Dario OS desde o cursor `since` (use `next_seq` da resposta
        anterior). `gap: true` indica eventos perdidos entre as chamadas."""
        return buffer.since(since, limit)

    return mcp
