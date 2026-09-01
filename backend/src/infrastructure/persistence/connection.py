"""SQLAlchemy async engine, session factory, and base model class."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlite3 import Connection as SQLite3Connection

from typing import Any, AsyncGenerator
from contextlib import asynccontextmanager
import os
from config.settings import settings

# Prefer DATABASE_URL from settings/env if configured; fallback to local SQLite
if settings.DATABASE_URL:
    DATABASE_URL = settings.DATABASE_URL
else:
    DB_DIR = os.path.join(os.getcwd(), "data")
    os.makedirs(DB_DIR, exist_ok=True)
    DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(DB_DIR, 'trading_bot.db')}"

# Configure engine arguments based on dialect
engine_kwargs: dict[str, Any] = {"echo": False}
if DATABASE_URL.startswith("postgresql"):
    engine_kwargs.update({
        "pool_size": 20,
        "max_overflow": 10,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    })

engine = create_async_engine(DATABASE_URL, **engine_kwargs)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign-key enforcement on every new SQLite connection."""
    if isinstance(dbapi_connection, SQLite3Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def init_db():
    """Create all tables defined in models if they do not yet exist."""
    import src.infrastructure.persistence.models  # ensure models loaded

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async session scope."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency helper to yield an async session."""
    async with AsyncSessionLocal() as session:
        yield session