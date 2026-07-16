"""Async SQLAlchemy engine and session management."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from utils.config import get_settings

settings = get_settings()

_engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}
if not settings.database_url.startswith("sqlite"):
    # SQLite uses its own pooling; for Postgres, size the pool for concurrency.
    _engine_kwargs.update(
        pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow
    )

engine = create_async_engine(settings.database_url, **_engine_kwargs)

async_session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session per request."""
    async with async_session_factory() as session:
        yield session
