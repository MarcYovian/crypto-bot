"""Alembic environment configuration for async migrations."""

import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import settings dan Base metadata
try:
    from config.settings import settings
    database_url = settings.DATABASE_URL
except ImportError:
    import os
    database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/cryptobot")

from src.database.connection import Base
import src.database.models  # Ensure all models are loaded for Alembic metadata


# Konfigurasi Alembic Config Object
config = context.config

# Set sqlalchemy.url dari environment / settings
config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata ORM yang akan dibandingkan dengan database nyata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Jalankan migrasi dalam mode 'offline' (menghasilkan file SQL tanpa koneksi langsung)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Melakukan proses perbandingan skema (autogenerate) dan eksekusi migrasi."""
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        compare_type=True  # Deteksi perubahan tipe data kolom
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Membuka koneksi async via asyncpg untuk menjalankan engine Alembic."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Jalankan migrasi dalam mode 'online' (terhubung langsung ke PostgreSQL)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()