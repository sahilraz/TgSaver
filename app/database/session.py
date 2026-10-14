"""Database session management and initialization."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings
from app.database.models import Base

# Ensure SQLite directory exists if local SQLite is configured
if settings.is_sqlite:
    sqlite_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    if "/" in sqlite_path or "\\" in sqlite_path:
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    # asyncpg / postgres pool settings; SQLite does not support custom pool size
    **({} if settings.is_sqlite else {"pool_size": 10, "max_overflow": 20}),
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields a transactional async database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def reset_db() -> None:
    """Drops all existing database tables and recreates fresh schema (manual one-time use only)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def init_db() -> None:
    """Initializes tables in database without dropping existing data."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)




async def close_db() -> None:
    """Disposes database connection pool on shutdown."""
    await engine.dispose()
