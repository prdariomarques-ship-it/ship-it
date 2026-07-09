"""Async SQLAlchemy engine and session management."""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from utils.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session per request."""
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Create tables that don't exist yet (development convenience).

    In production schema changes should go through migrations instead.
    """
    from database.base import Base
    import models  # noqa: F401  (register all models on the metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
