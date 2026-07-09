"""Dario OS — API entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import jobs.handlers  # noqa: F401 - register the built-in job handlers
from agents.router import router as agents_router
from api.routes import (
    calendar_router,
    church_router,
    contacts_router,
    dashboard_router,
    logs_router,
    messages_router,
    notes_router,
    store_router,
    tasks_router,
)
from api.whatsapp import router as whatsapp_router
from auth.router import router as auth_router
from chat.router import router as chat_router
from jobs.router import router as jobs_router
from jobs.worker import job_worker
from memory.router import router as memory_router
from observability import health_router, metrics_middleware, metrics_router
from services.rate_limit import rate_limiter
from utils.config import get_settings
from utils.logging import configure_logging, get_logger
from webhooks.router import router as webhooks_router
from workflows.router import router as workflows_router

logger = get_logger(__name__)

OPENAPI_TAGS = [
    {"name": "auth", "description": "Registro, login, refresh token e perfil."},
    {"name": "chat", "description": "Conversa com agentes IA (planner + executor + memória)."},
    {"name": "agents", "description": "Agentes disponíveis e execução direta com function calling."},
    {"name": "memory", "description": "Memória permanente semântica (Qdrant + embeddings)."},
    {"name": "whatsapp", "description": "Envio de mensagens via provider configurado."},
    {"name": "webhooks", "description": "Entrada de eventos externos (WhatsApp)."},
    {"name": "workflows", "description": "Disparo de automações no n8n."},
    {"name": "jobs", "description": "Fila de trabalhos em background (admin)."},
    {"name": "health", "description": "Liveness e readiness."},
    {"name": "observability", "description": "Métricas Prometheus."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(json_output=settings.log_json)
    if settings.jobs_enabled and settings.environment != "test":
        job_worker.start()
    logger.info("%s v%s started (%s)", settings.app_name, settings.app_version, settings.environment)
    yield
    if settings.jobs_enabled and settings.environment != "test":
        await job_worker.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Sistema operacional pessoal baseado em IA — API central do Dario OS.\n\n"
            "Autentique-se via `/api/auth/login` e use o `access_token` como Bearer token. "
            "Tokens expiram rápido; renove com `/api/auth/refresh`."
        ),
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.middleware("http")(metrics_middleware)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if not await rate_limiter.is_allowed(client_ip):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded"},
            )
        return await call_next(request)

    app.include_router(health_router)
    app.include_router(metrics_router)

    prefix = settings.api_prefix
    app.include_router(auth_router, prefix=prefix)
    app.include_router(chat_router, prefix=prefix)
    app.include_router(memory_router, prefix=prefix)
    app.include_router(agents_router, prefix=prefix)
    app.include_router(workflows_router, prefix=prefix)
    app.include_router(webhooks_router, prefix=prefix)
    app.include_router(whatsapp_router, prefix=prefix)
    app.include_router(jobs_router, prefix=prefix)
    app.include_router(contacts_router, prefix=prefix)
    app.include_router(messages_router, prefix=prefix)
    app.include_router(tasks_router, prefix=prefix)
    app.include_router(calendar_router, prefix=prefix)
    app.include_router(notes_router, prefix=prefix)
    app.include_router(church_router, prefix=prefix)
    app.include_router(store_router, prefix=prefix)
    app.include_router(logs_router, prefix=prefix)
    app.include_router(dashboard_router, prefix=prefix)

    return app


app = create_app()
