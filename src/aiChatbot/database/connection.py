"""
Async PostgreSQL connection management via SQLAlchemy 2.0.

Usage:
    await init_database(database_url)
    async with get_db_session() as session:
        result = await session.execute(...)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Singleton-style manager for the async PostgreSQL connection.
    Holds the engine and session factory for the application lifetime.
    """

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def init(self, database_url: str, echo: bool = False) -> None:
        """
        Initialize the async engine and create all tables.

        Args:
            database_url: postgresql+asyncpg://user:pass@host:port/dbname
            echo: Log all SQL statements (useful for debugging, keep False in prod)
        """
        if self._engine is not None:
            logger.warning("DatabaseManager already initialized — skipping")
            return

        logger.info("Initializing PostgreSQL connection...")

        self._engine = create_async_engine(
            database_url,
            echo=echo,
            # Bağlantı havuzu ayarları — WhatsApp chatbot için dengeli değerler
            pool_size=5,            # Sabit havuz boyutu
            max_overflow=10,        # Ek bağlantılara izin ver (anlık yük patlamaları için)
            pool_pre_ping=True,     # Stale bağlantıları otomatik temizle
            pool_recycle=1800,      # 30 dakikada bir bağlantıyı yenile
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,  # commit sonrası objeler hâlâ erişilebilir kalsın
            autoflush=False,
            autocommit=False,
        )

        logger.info("PostgreSQL engine created")

    async def create_tables(self) -> None:
        """Create all ORM tables if they don't exist."""
        if self._engine is None:
            raise RuntimeError("DatabaseManager not initialized. Call init() first.")

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified ✓")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Async context manager that yields a database session.

        Usage:
            async with db_manager.session() as session:
                result = await session.execute(select(UserModel))
        """
        if self._session_factory is None:
            raise RuntimeError("DatabaseManager not initialized. Call init() first.")

        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def close(self) -> None:
        """Dispose the engine and release all connections."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database connections closed")

    @property
    def is_initialized(self) -> bool:
        return self._engine is not None


# Uygulama genelinde tek bir DatabaseManager instance
db_manager = DatabaseManager()


async def init_database(database_url: str, echo: bool = False) -> None:
    """Convenience function to initialize the global db_manager."""
    await db_manager.init(database_url, echo=echo)
    await db_manager.create_tables()


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Convenience context manager using the global db_manager."""
    async with db_manager.session() as session:
        yield session
