"""Dario OS — API entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import jobs.handlers  # noqa: F401 - register the built-in job handlers
from admin.router import router as admin_router
from agents.router import router as agents_router
from jobs.handlers import register_event_subscribers
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
from gcalendar.router import router as gcalendar_router
from gcontacts.router import router as gcontacts_router
from gdrive.router import router as gdrive_router
from jobs.router import router as jobs_router
from jobs.worker import job_worker
from mail.router import router as mail_router
from memory.router import router as memory_router
from middleware.error_sanitization import ErrorSanitizationMiddleware
from middleware.request_size_limit import RequestSizeLimitMiddleware
from middleware.security_headers import SecurityHeadersMiddleware
from observability import RequestIDMiddleware, health_router, metrics_middleware, metrics_router, setup_tracing
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
    {"name": "mail", "description": "Integração Gmail (somente leitura) — conexão OAuth admin-only."},
    {"name": "gcalendar", "description": "Integração Google Calendar — conexão OAuth admin-only."},
    {"name": "gcontacts", "description": "Integração Google Contacts — conexão OAuth admin-only."},
    {"name": "gdrive", "description": "Integração Google Drive (base de conhecimento) — conexão OAuth admin-only."},
    {"name": "health", "description": "Liveness e readiness."},
    {"name": "observability", "description": "Métricas Prometheus."},
    {"name": "admin", "description": "Dashboard administrativo (somente leitura) — admin-only."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(json_output=settings.log_json)
    register_event_subscribers()
    if settings.jobs_enabled and settings.environment != "test":
        job_worker.start()
    logger.info("%s v%s started (%s)", settings.app_name, settings.app_version, settings.environment)
    yield
    if settings.jobs_enabled and settings.environment != "test":
        await job_worker.stop()


def _validate_production_settings(settings) -> None:
    """Refuse to boot in production with a missing/weak JWT secret or webhook secret.

    WEBHOOK_SECRET is the only authentication most WhatsApp providers have
    (OpenWA/Baileys/Evolution have no signature scheme of their own — see
    `providers/whatsapp/base.py::verify_signature`), so an unset/weak value
    here leaves /api/webhooks/whatsapp open to unauthenticated requests that
    trigger the full Cognitive Pipeline. Same bar as JWT_SECRET (>= 32 chars),
    same fail-closed behavior.
    """
    if settings.environment != "production":
        return
    if settings.jwt_secret in ("", "change-me-in-production") or len(settings.jwt_secret) < 32:
        raise RuntimeError(
            "JWT_SECRET must be set to a strong value (>= 32 chars) in production; "
            "generate one with: openssl rand -hex 32"
        )
    if not settings.webhook_secret or len(settings.webhook_secret) < 32:
        raise RuntimeError(
            "WEBHOOK_SECRET must be set to a strong value (>= 32 chars) in production; "
            "generate one with: openssl rand -hex 32"
        )


# Never rate-limit probes or scrapers: a busy client must not blind monitoring.
_RATE_LIMIT_EXEMPT_PREFIXES = ("/health", "/metrics")


def create_app() -> FastAPI:
    settings = get_settings()
    _validate_production_settings(settings)
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

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next) -> Response:
        if request.url.path.startswith(_RATE_LIMIT_EXEMPT_PREFIXES):
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        if not await rate_limiter.is_allowed(client_ip):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded"},
            )
        return await call_next(request)

    # Registered after (= outermost), so 429s from the rate limiter are counted too.
    app.middleware("http")(metrics_middleware)

    # Outermost of all: the request id must be set before CORS/rate-limit/
    # metrics run, so their own log lines (and an early 429/403 response)
    # already carry it too.
    app.add_middleware(RequestIDMiddleware)

    # P7 Security hardening middleware (in reverse order of execution):
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(ErrorSanitizationMiddleware)

    setup_tracing(
        app,
        enabled=settings.otel_enabled,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        service_name=settings.app_name,
    )

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
    app.include_router(mail_router, prefix=prefix)
    app.include_router(gcalendar_router, prefix=prefix)
    app.include_router(gcontacts_router, prefix=prefix)
    app.include_router(gdrive_router, prefix=prefix)
    app.include_router(admin_router, prefix=prefix)

    return app


app = create_app()
