"""Health endpoints: liveness (process up) and readiness (dependencies)."""

import asyncio

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from utils.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/live")
async def liveness() -> dict:
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


async def _check_database() -> str:
    from database.session import engine

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return "ok"


async def _check_redis() -> str:
    from redis import asyncio as aioredis

    client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await client.ping()
    finally:
        await client.aclose()
    return "ok"


async def _check_qdrant() -> str:
    from memory.service import memory_service

    await memory_service.client.get_collections()
    return "ok"


class WhatsAppProviderUnhealthy(RuntimeError):
    pass


async def _check_whatsapp() -> str:
    from observability.metrics import record_whatsapp_session_status
    from providers.whatsapp.factory import get_whatsapp_provider

    provider = get_whatsapp_provider()
    healthy = await provider.health_check()
    record_whatsapp_session_status(provider.name, connected=healthy)
    if not healthy:
        raise WhatsAppProviderUnhealthy(provider.name)
    return "ok"


@router.get("/health/ready")
async def readiness(response: Response) -> dict:
    """Database is required; Redis, Qdrant and the WhatsApp provider degrade
    gracefully, so they only mark the service as 'degraded' instead of
    failing readiness."""
    checks: dict[str, str] = {}

    required_ok = True
    for name, check, required in (
        ("database", _check_database, True),
        ("redis", _check_redis, False),
        ("qdrant", _check_qdrant, False),
        ("whatsapp", _check_whatsapp, False),
    ):
        try:
            checks[name] = await asyncio.wait_for(check(), timeout=5)
        except Exception as exc:  # noqa: BLE001 - report any dependency failure
            checks[name] = f"error: {type(exc).__name__}"
            if required:
                required_ok = False

    degraded = any(value.startswith("error") for value in checks.values())
    if not required_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall = "unavailable"
    else:
        overall = "degraded" if degraded else "ok"
    return {"status": overall, "checks": checks}
