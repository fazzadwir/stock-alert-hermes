"""
Unit tests untuk WatchlistRepository.
Menggunakan in-memory SQLite (aiosqlite) — terisolasi dan cepat.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.storage.models import Base
from app.storage.watchlist_repository import WatchlistRepository


@pytest_asyncio.fixture
async def repo():
    """Fixture repository dengan database SQLite in-memory."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    repository = WatchlistRepository(session_factory=session_factory)
    yield repository
    await engine.dispose()


class TestWatchlistRepository:
    @pytest.mark.asyncio
    async def test_add_and_get_item(self, repo: WatchlistRepository):
        success, status = await repo.add_item(1001, "BBCA.JK", "Bank BCA")
        assert success is True
        assert status == "added"

        items = await repo.get_user_watchlist(1001)
        assert len(items) == 1
        assert items[0].symbol == "BBCA.JK"
        assert items[0].note == "Bank BCA"
        assert items[0].user_id == 1001

    @pytest.mark.asyncio
    async def test_duplicate_item_rejected(self, repo: WatchlistRepository):
        await repo.add_item(1001, "AAPL")
        success, status = await repo.add_item(1001, "aapl")  # Case insensitive handling
        assert success is False
        assert status == "already_exists"

        items = await repo.get_user_watchlist(1001)
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_different_users_separate_watchlists(self, repo: WatchlistRepository):
        await repo.add_item(1001, "BBCA.JK")
        await repo.add_item(1002, "BBCA.JK")

        items1 = await repo.get_user_watchlist(1001)
        items2 = await repo.get_user_watchlist(1002)
        assert len(items1) == 1
        assert len(items2) == 1

    @pytest.mark.asyncio
    async def test_count_user_watchlist(self, repo: WatchlistRepository):
        assert await repo.count_user_watchlist(1001) == 0
        await repo.add_item(1001, "BBCA.JK")
        await repo.add_item(1001, "AAPL")
        assert await repo.count_user_watchlist(1001) == 2

    @pytest.mark.asyncio
    async def test_is_in_watchlist(self, repo: WatchlistRepository):
        assert await repo.is_in_watchlist(1001, "BBCA.JK") is False
        await repo.add_item(1001, "BBCA.JK")
        assert await repo.is_in_watchlist(1001, "bbca.jk") is True
        assert await repo.is_in_watchlist(1001, "AAPL") is False

    @pytest.mark.asyncio
    async def test_remove_existing_item(self, repo: WatchlistRepository):
        await repo.add_item(1001, "BBCA.JK")
        deleted = await repo.remove_item(1001, "BBCA.JK")
        assert deleted is True

        items = await repo.get_user_watchlist(1001)
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent_item(self, repo: WatchlistRepository):
        deleted = await repo.remove_item(1001, "NONEXISTENT")
        assert deleted is False
