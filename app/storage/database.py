"""
MarketPulse — app/storage/database.py
Pengelolaan koneksi database asynchronous (SQLite + aiosqlite).
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.storage.models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manager lifecycle database asynchronous.
    Menginisialisasi engine, sessionmaker, dan memastikan skema tabel dibuat.
    """

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._ensure_sqlite_directory(database_url)

        self.engine: AsyncEngine = create_async_engine(
            database_url,
            echo=False,
            future=True,
        )
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    @staticmethod
    def _ensure_sqlite_directory(database_url: str) -> None:
        """Pastikan direktori untuk SQLite database file ada."""
        if "sqlite" in database_url and "///" in database_url and ":memory:" not in database_url:
            path_str = database_url.split("///")[-1]
            db_path = Path(path_str).resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug("Memastikan direktori database SQLite ada: %s", db_path.parent)

    async def init_db(self) -> None:
        """Buat semua tabel jika belum ada."""
        logger.info("Menginisialisasi tabel database...")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Inisialisasi tabel database selesai.")

    async def close(self) -> None:
        """Tutup koneksi engine."""
        await self.engine.dispose()
        logger.info("Koneksi database ditutup.")
