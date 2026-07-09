"""Test fixtures: in-memory SQLite database and an authenticated HTTP client."""
import os

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["JWT_SECRET"] = "test-secret-key-with-enough-bytes-for-hs256"
os.environ["OPENAI_API_KEY"] = ""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database.base import Base
from database.session import get_db
from main import app
import models  # noqa: F401 - register models on the metadata


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_local_caches():
    """Cache/rate-limit singletons survive between tests; clear their local state."""
    from services.cache import cache_service
    from services.rate_limit import rate_limiter

    cache_service._local.clear()
    rate_limiter._local_windows.clear()
    yield
    cache_service._local.clear()


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
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
        json={"email": "dario@example.com", "full_name": "Dario", "password": "supersecret1"},
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": "dario@example.com", "password": "supersecret1"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
