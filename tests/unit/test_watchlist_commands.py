"""
Unit tests untuk handler command watchlist (/add, /remove, /watchlist, /market).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.commands import BotCommandHandlers
from app.domain.market_schemas import DataStatus, InstrumentType, QuoteResult
from app.storage.models import WatchlistItem


def make_mock_update(user_id: int):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = f"user_{user_id}"
    update.message = AsyncMock()
    return update


def make_mock_context(args: list[str] | None = None):
    ctx = MagicMock()
    ctx.args = args or []
    return ctx


@pytest.fixture
def mock_market():
    m = MagicMock()
    m.get_quote = AsyncMock()
    return m


@pytest.fixture
def mock_repo():
    r = MagicMock()
    r.get_user_watchlist = AsyncMock(return_value=[])
    r.count_user_watchlist = AsyncMock(return_value=0)
    r.is_in_watchlist = AsyncMock(return_value=False)
    r.add_item = AsyncMock(return_value=(True, "added"))
    r.remove_item = AsyncMock(return_value=True)
    return r


@pytest.fixture
def handlers(mock_market, mock_repo):
    return BotCommandHandlers(
        market_service=mock_market,
        allowed_ids=frozenset({1001}),
        watchlist_repo=mock_repo,
        max_watchlist_assets=5,
    )


class TestWatchlistCommands:
    @pytest.mark.asyncio
    async def test_watchlist_denied_user(self, handlers):
        update = make_mock_update(9999)
        ctx = make_mock_context()
        await handlers.cmd_watchlist(update, ctx)
        update.message.reply_text.assert_called_once()
        assert "Akses ditolak" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_watchlist_empty(self, handlers, mock_repo):
        mock_repo.get_user_watchlist.return_value = []
        update = make_mock_update(1001)
        ctx = make_mock_context()
        await handlers.cmd_watchlist(update, ctx)
        reply = update.message.reply_text.call_args[0][0]
        assert "Kosong" in reply

    @pytest.mark.asyncio
    async def test_watchlist_with_items(self, handlers, mock_repo, mock_market):
        item = WatchlistItem(id=1, user_id=1001, symbol="BBCA.JK", note="Banking")
        mock_repo.get_user_watchlist.return_value = [item]

        quote = QuoteResult(
            symbol="BBCA.JK",
            price=Decimal("6050"),
            currency="IDR",
            instrument_type=InstrumentType.EQUITY,
            source="yfinance",
            data_status=DataStatus.LAST_CLOSE,
        )
        mock_market.get_quote.return_value = quote

        loading_msg = AsyncMock()
        update = make_mock_update(1001)
        update.message.reply_text.return_value = loading_msg
        ctx = make_mock_context()

        await handlers.cmd_watchlist(update, ctx)
        loading_msg.edit_text.assert_called_once()
        text = loading_msg.edit_text.call_args[0][0]
        assert "BBCA.JK" in text
        assert "Rp 6,050" in text

    @pytest.mark.asyncio
    async def test_add_no_args_shows_usage(self, handlers):
        update = make_mock_update(1001)
        ctx = make_mock_context([])
        await handlers.cmd_add(update, ctx)
        assert "Penggunaan" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_add_limit_reached(self, handlers, mock_repo):
        mock_repo.count_user_watchlist.return_value = 5  # limit is 5
        update = make_mock_update(1001)
        ctx = make_mock_context(["BBCA.JK"])
        await handlers.cmd_add(update, ctx)
        assert "mencapai batas maksimal" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_add_already_in_watchlist(self, handlers, mock_repo):
        mock_repo.is_in_watchlist.return_value = True
        update = make_mock_update(1001)
        ctx = make_mock_context(["BBCA.JK"])
        await handlers.cmd_add(update, ctx)
        assert "sudah ada" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_add_invalid_market_symbol(self, handlers, mock_repo, mock_market):
        mock_repo.is_in_watchlist.return_value = False
        mock_market.get_quote.return_value = QuoteResult(
            symbol="INVALID",
            error="invalid_symbol",
            data_status=DataStatus.UNAVAILABLE,
            source="yfinance",
        )
        loading_msg = AsyncMock()
        update = make_mock_update(1001)
        update.message.reply_text.return_value = loading_msg
        ctx = make_mock_context(["INVALID"])

        await handlers.cmd_add(update, ctx)
        loading_msg.edit_text.assert_called_once()
        assert "tidak ditemukan" in loading_msg.edit_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_add_success(self, handlers, mock_repo, mock_market):
        mock_repo.is_in_watchlist.return_value = False
        mock_repo.add_item.return_value = (True, "added")
        mock_market.get_quote.return_value = QuoteResult(
            symbol="BBCA.JK",
            price=Decimal("6050"),
            currency="IDR",
            instrument_type=InstrumentType.EQUITY,
            source="yfinance",
        )
        loading_msg = AsyncMock()
        update = make_mock_update(1001)
        update.message.reply_text.return_value = loading_msg
        ctx = make_mock_context(["BBCA.JK", "Core", "Holding"])

        await handlers.cmd_add(update, ctx)
        mock_repo.add_item.assert_called_once_with(1001, "BBCA.JK", "Core Holding")
        assert "berhasil ditambahkan" in loading_msg.edit_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_remove_no_args_shows_usage(self, handlers):
        update = make_mock_update(1001)
        ctx = make_mock_context([])
        await handlers.cmd_remove(update, ctx)
        assert "Penggunaan" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_remove_success(self, handlers, mock_repo):
        mock_repo.remove_item.return_value = True
        update = make_mock_update(1001)
        ctx = make_mock_context(["BBCA.JK"])
        await handlers.cmd_remove(update, ctx)
        mock_repo.remove_item.assert_called_once_with(1001, "BBCA.JK")
        assert "berhasil dihapus" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_remove_not_found(self, handlers, mock_repo):
        mock_repo.remove_item.return_value = False
        update = make_mock_update(1001)
        ctx = make_mock_context(["BBCA.JK"])
        await handlers.cmd_remove(update, ctx)
        assert "tidak ditemukan" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_market_summary(self, handlers, mock_repo, mock_market):
        item = WatchlistItem(id=1, user_id=1001, symbol="AAPL")
        mock_repo.get_user_watchlist.return_value = [item]

        quote = QuoteResult(
            symbol="AAPL",
            price=Decimal("200"),
            previous_close=Decimal("190"),
            price_change=Decimal("10"),
            price_change_pct=Decimal("5.26"),
            currency="USD",
            instrument_type=InstrumentType.EQUITY,
            source="yfinance",
        )
        mock_market.get_quote.return_value = quote

        loading_msg = AsyncMock()
        update = make_mock_update(1001)
        update.message.reply_text.return_value = loading_msg
        ctx = make_mock_context()

        await handlers.cmd_market(update, ctx)
        loading_msg.edit_text.assert_called_once()
        text = loading_msg.edit_text.call_args[0][0]
        assert "Snapshot Pasar" in text
        assert "AAPL" in text
        assert "Naik" in text
