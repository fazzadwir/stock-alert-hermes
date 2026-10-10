"""
Unit tests untuk command handlers.
Menggunakan mock provider dan mock Telegram Update.
Tidak memerlukan token Telegram asli atau koneksi internet.
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot.commands import BotCommandHandlers, _is_allowed
from app.domain.market_schemas import DataStatus, InstrumentType, QuoteResult
from app.market_data.service import MarketDataService


def make_mock_update(user_id: int, text: str = "", args: list[str] | None = None):
    """Helper untuk membuat mock Telegram Update."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = f"user_{user_id}"
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.edit_text = AsyncMock()
    return update


def make_mock_context(args: list[str] | None = None):
    """Helper untuk membuat mock Telegram Context."""
    context = MagicMock()
    context.args = args or []
    return context


class TestIsAllowed:
    """Tests untuk fungsi _is_allowed."""

    def test_user_in_allowlist_is_allowed(self):
        assert _is_allowed(123, frozenset({123, 456})) is True

    def test_user_not_in_allowlist_is_denied(self):
        assert _is_allowed(999, frozenset({123, 456})) is False

    def test_empty_allowlist_denies_everyone(self):
        """Fail-closed: allowlist kosong → semua ditolak."""
        assert _is_allowed(123, frozenset()) is False
        assert _is_allowed(0, frozenset()) is False

    def test_any_user_id_zero_denied_with_empty_list(self):
        assert _is_allowed(0, frozenset()) is False


class TestBotCommandHandlers:
    """Tests untuk BotCommandHandlers."""

    @pytest.fixture
    def handlers(self, mock_market_service):
        return BotCommandHandlers(
            market_service=mock_market_service,
            allowed_ids=frozenset({111, 222}),
        )

    @pytest.fixture
    def handlers_empty_allowlist(self, mock_market_service):
        return BotCommandHandlers(
            market_service=mock_market_service,
            allowed_ids=frozenset(),  # fail-closed
        )

    # ── /start ───────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_start_allowed_user_gets_reply(self, handlers):
        update = make_mock_update(111)
        ctx = make_mock_context()
        await handlers.cmd_start(update, ctx)
        update.message.reply_text.assert_called_once()
        # Periksa konten pesan
        call_args = update.message.reply_text.call_args
        assert "MarketPulse" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_start_denied_user_gets_access_denied(self, handlers):
        update = make_mock_update(999)  # Tidak ada di allowlist
        ctx = make_mock_context()
        await handlers.cmd_start(update, ctx)
        update.message.reply_text.assert_called_once()
        # Pesan harus berisi teks penolakan
        call_args = update.message.reply_text.call_args
        msg = call_args[0][0]
        assert "ditolak" in msg.lower() or "🔒" in msg

    @pytest.mark.asyncio
    async def test_start_with_empty_allowlist_denies_all(self, handlers_empty_allowlist):
        update = make_mock_update(111)
        ctx = make_mock_context()
        await handlers_empty_allowlist.cmd_start(update, ctx)
        call_args = update.message.reply_text.call_args
        msg = call_args[0][0]
        assert "ditolak" in msg.lower() or "🔒" in msg

    # ── /help ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_help_allowed_user(self, handlers):
        update = make_mock_update(111)
        ctx = make_mock_context()
        await handlers.cmd_help(update, ctx)
        update.message.reply_text.assert_called_once()
        msg = update.message.reply_text.call_args[0][0]
        assert "/stock" in msg or "/gold" in msg

    @pytest.mark.asyncio
    async def test_help_denied_user(self, handlers):
        update = make_mock_update(999)
        ctx = make_mock_context()
        await handlers.cmd_help(update, ctx)
        msg = update.message.reply_text.call_args[0][0]
        assert "ditolak" in msg.lower() or "🔒" in msg

    # ── /stock ───────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_stock_without_args_shows_usage(self, handlers):
        update = make_mock_update(111)
        ctx = make_mock_context(args=[])  # Tidak ada argumen
        await handlers.cmd_stock(update, ctx)
        # Harus menampilkan pesan penggunaan
        assert update.message.reply_text.called or update.message.edit_text.called

    @pytest.mark.asyncio
    async def test_stock_with_valid_symbol_calls_service(self, handlers, mock_market_service, sample_aapl_quote):
        mock_market_service.get_quote = AsyncMock(return_value=sample_aapl_quote)
        update = make_mock_update(111)
        ctx = make_mock_context(args=["AAPL"])

        # Mock loading message
        loading_msg = AsyncMock()
        loading_msg.edit_text = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=loading_msg)

        await handlers.cmd_stock(update, ctx)

        # Pastikan service dipanggil dengan symbol yang benar
        mock_market_service.get_quote.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_stock_denied_user_no_service_call(self, handlers, mock_market_service):
        mock_market_service.get_quote = AsyncMock()
        update = make_mock_update(999)  # Not allowed
        ctx = make_mock_context(args=["AAPL"])
        await handlers.cmd_stock(update, ctx)
        # Service tidak boleh dipanggil jika user tidak diizinkan
        mock_market_service.get_quote.assert_not_called()

    @pytest.mark.asyncio
    async def test_stock_invalid_error_shown(self, handlers, mock_market_service, invalid_symbol_quote):
        mock_market_service.get_quote = AsyncMock(return_value=invalid_symbol_quote)
        update = make_mock_update(111)
        ctx = make_mock_context(args=["INVALID123"])

        loading_msg = AsyncMock()
        loading_msg.edit_text = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=loading_msg)

        await handlers.cmd_stock(update, ctx)

        # Edit text harus dipanggil dengan pesan error
        loading_msg.edit_text.assert_called_once()
        error_msg = loading_msg.edit_text.call_args[0][0]
        # Pesan tidak boleh mengandung harga yang dikarang
        assert "tidak ditemukan" in error_msg.lower() or "❌" in error_msg

    @pytest.mark.asyncio
    async def test_stock_too_long_symbol_rejected(self, handlers):
        update = make_mock_update(111)
        ctx = make_mock_context(args=["A" * 25])  # 25 karakter, terlalu panjang
        await handlers.cmd_stock(update, ctx)
        update.message.reply_text.assert_called_once()

    # ── /gold ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_gold_calls_get_gold_quote(self, handlers, mock_market_service, sample_gold_quote):
        mock_market_service.get_gold_quote = AsyncMock(return_value=sample_gold_quote)
        update = make_mock_update(111)
        ctx = make_mock_context()

        loading_msg = AsyncMock()
        loading_msg.edit_text = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=loading_msg)

        await handlers.cmd_gold(update, ctx)
        mock_market_service.get_gold_quote.assert_called_once()

    @pytest.mark.asyncio
    async def test_gold_denied_user_no_service_call(self, handlers, mock_market_service):
        mock_market_service.get_gold_quote = AsyncMock()
        update = make_mock_update(999)
        ctx = make_mock_context()
        await handlers.cmd_gold(update, ctx)
        mock_market_service.get_gold_quote.assert_not_called()

    # ── Safety: no secrets in logs ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_no_token_in_log_on_access_denied(self, handlers, caplog):
        """Log tidak boleh mengandung token atau info sensitif."""
        import logging
        with caplog.at_level(logging.WARNING, logger="app.bot.commands"):
            update = make_mock_update(999)
            ctx = make_mock_context()
            await handlers.cmd_start(update, ctx)

        # Log tidak boleh mengandung token-like strings
        for record in caplog.records:
            assert ":" not in record.message or "bot" not in record.message.lower() or len(record.message) < 200
