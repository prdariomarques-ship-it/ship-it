"""Test fixtures: in-memory SQLite database and an authenticated HTTP client."""

import os
import uuid

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["JWT_SECRET"] = "test-secret-key-with-enough-bytes-for-hs256"
os.environ["WEBHOOK_SECRET"] = ""
os.environ["OPENAI_API_KEY"] = ""
# Unmocked provider calls in tests hit an unreachable localhost gateway by
# design (no real WhatsApp/n8n running); keep retry/backoff from adding
# multi-second delays to every one of those expected failures.
os.environ["WHATSAPP_REQUEST_MAX_ATTEMPTS"] = "1"
os.environ["WHATSAPP_REQUEST_BACKOFF_SECONDS"] = "0"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.base import Base
from database.session import get_db
from main import app
import models  # noqa: F401 - register models on the metadata


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_local_caches():
    """Cache/rate-limit/event-bus singletons survive between tests; reset their state."""
    from events.bus import event_bus
    from services.cache import cache_service
    from services.rate_limit import rate_limiter

    cache_service._local.clear()
    rate_limiter._local_windows.clear()
    event_bus.unsubscribe_all()
    yield
    cache_service._local.clear()
    event_bus.unsubscribe_all()


@pytest_asyncio.fixture
async def db_engine(tmp_path):
    # A real file (not `:memory:` + StaticPool, and not a shared-cache memory
    # URI either) with WAL mode, because the job worker now opens genuinely
    # concurrent sessions via asyncio.gather (one per due job). StaticPool
    # forces every session through one shared connection object (undefined
    # behaviour under real concurrent use); shared-cache in-memory mode
    # supports two concurrent writers via the busy-timeout but still throws
    # `InvalidRequestError: Could not refresh instance` once 3+ sessions
    # write at once (SQLITE_LOCKED from shared-cache table locking isn't
    # retried by the busy handler the way SQLITE_BUSY is). WAL mode is
    # SQLite's actual answer to concurrent writers, but it isn't supported
    # for in-memory databases — hence a real (temp, per-test, auto-cleaned
    # by pytest's tmp_path) file on disk.
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client) -> dict[str, str]:
    await client.post(
        "/api/auth/register",
        json={
            "email": "dario@example.com",
            "full_name": "Dario",
            "password": "supersecret1",
        },
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": "dario@example.com", "password": "supersecret1"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
