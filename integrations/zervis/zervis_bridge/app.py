"""ASGI: servidor MCP com autenticação Bearer + assinante de eventos."""

from __future__ import annotations

import asyncio
import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .buffer import EventBuffer
from .client import DarioOSClient
from .config import Settings
from .subscriber import EventSubscriber
from .tools import build_server


class BearerAuth:
    """Middleware ASGI: 401 sem `Authorization: Bearer <token>` válido.

    Comparação em tempo constante. `/healthz` é a única rota pública (probe do
    compose) e não expõe dados.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == "/healthz":
            await self._app(scope, receive, send)
            return
        header = dict(scope["headers"]).get(b"authorization", b"")
        scheme, _, presented = header.partition(b" ")
        if scheme.lower() != b"bearer" or not hmac.compare_digest(
            presented.strip(), self._token
        ):
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)


def create_app(settings: Settings, client: DarioOSClient | None = None) -> Starlette:
    client = client or DarioOSClient(
        settings.darioos_api_url,
        settings.darioos_token.get_secret_value(),
        timeout=settings.request_timeout_seconds,
        max_attempts=settings.request_max_attempts,
        backoff=settings.request_backoff_seconds,
    )
    buffer = EventBuffer(settings.buffer_max_events, settings.buffer_ttl_seconds)
    subscriber = EventSubscriber(
        settings.redis_url,
        settings.events_channel,
        buffer,
        backoff_max=settings.subscriber_backoff_max_seconds,
    )
    mcp = build_server(client, buffer, subscriber, settings.allowed_hosts)
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        task = asyncio.create_task(subscriber.run(), name="event-subscriber")
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await client.aclose()

    async def healthz(_request: object) -> Response:
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[Route("/healthz", healthz), Mount("/", app=mcp_app)],
        lifespan=lifespan,
    )
    app.add_middleware(BearerAuth, token=settings.mcp_token.get_secret_value())
    return app
