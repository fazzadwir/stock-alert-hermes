"""
MarketPulse — app/storage/watchlist_repository.py
Repository untuk operasi data watchlist user (CRUD).
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.storage.models import WatchlistItem

logger = logging.getLogger(__name__)


class WatchlistRepository:
    """Repository asynchronous untuk watchlist."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add_item(
        self,
        user_id: int,
        symbol: str,
        note: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Menambahkan simbol ke watchlist user.
        Returns:
            (True, "added") jika sukses
            (False, "already_exists") jika sudah ada di watchlist
        """
        symbol_upper = symbol.upper().strip()
        async with self._session_factory() as session:
            async with session.begin():
                stmt = select(WatchlistItem).where(
                    WatchlistItem.user_id == user_id,
                    WatchlistItem.symbol == symbol_upper,
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing:
                    return False, "already_exists"

                item = WatchlistItem(
                    user_id=user_id,
                    symbol=symbol_upper,
                    note=note.strip() if note else None,
                )
                session.add(item)
                logger.info("User %s menambahkan %s ke watchlist", user_id, symbol_upper)
                return True, "added"

    async def remove_item(self, user_id: int, symbol: str) -> bool:
        """
        Menghapus simbol dari watchlist user.
        Returns True jika berhasil dihapus, False jika simbol tidak ditemukan.
        """
        symbol_upper = symbol.upper().strip()
        async with self._session_factory() as session:
            async with session.begin():
                stmt = delete(WatchlistItem).where(
                    WatchlistItem.user_id == user_id,
                    WatchlistItem.symbol == symbol_upper,
                )
                result = await session.execute(stmt)
                deleted = result.rowcount > 0
                if deleted:
                    logger.info("User %s menghapus %s dari watchlist", user_id, symbol_upper)
                return deleted

    async def get_user_watchlist(self, user_id: int) -> list[WatchlistItem]:
        """Mengambil seluruh daftar simbol di watchlist user, terurut tanggal dibuat."""
        async with self._session_factory() as session:
            stmt = (
                select(WatchlistItem)
                .where(WatchlistItem.user_id == user_id)
                .order_by(WatchlistItem.created_at.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_user_watchlist(self, user_id: int) -> int:
        """Menghitung total simbol di watchlist user."""
        async with self._session_factory() as session:
            stmt = select(func.count(WatchlistItem.id)).where(WatchlistItem.user_id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one() or 0

    async def is_in_watchlist(self, user_id: int, symbol: str) -> bool:
        """Cek apakah simbol ada di watchlist user."""
        symbol_upper = symbol.upper().strip()
        async with self._session_factory() as session:
            stmt = select(func.count(WatchlistItem.id)).where(
                WatchlistItem.user_id == user_id,
                WatchlistItem.symbol == symbol_upper,
            )
            result = await session.execute(stmt)
            count = result.scalar_one() or 0
            return count > 0
