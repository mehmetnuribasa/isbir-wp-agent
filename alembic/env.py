"""
Alembic migration environment — async PostgreSQL desteği.
DATABASE_URL .env dosyasından otomatik okunur.
"""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Proje src dizinini sys.path'e ekle ─────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

# ── .env dosyasını yükle ────────────────────────────────────────────────────────
load_dotenv(PROJECT_ROOT / ".env")

# ── ORM metadata'yı import et ──────────────────────────────────────────────────
from aiChatbot.database.models import Base  # noqa: E402

# Alembic Config nesnesi
config = context.config

# Logging ayarlarını yükle
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# SQLAlchemy metadata — autogenerate için
target_metadata = Base.metadata

# DATABASE_URL'yi env'den oku ve config'e yaz
database_url = os.environ.get("DATABASE_URL", "")
if not database_url:
    raise ValueError(
        "DATABASE_URL environment variable is not set. "
        "Check your .env file: DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname"
    )

# asyncpg → psycopg2'ye çevir (alembic offline mode için sync driver gerekir)
# Online mode (async) kendi engine'ini kullanacak
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """
    Offline migration — veritabanı bağlantısı olmadan SQL script üretir.
    asyncpg URL'sini sync psycopg2'ye çeviriyoruz.
    """
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Online async migration — gerçek PostgreSQL bağlantısıyla çalışır."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migration."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
