"""
Unit tests untuk Telegram command /ta (Technical Analysis).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.commands import BotCommandHandlers
from app.domain.market_schemas import TechnicalAnalysisResult


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
    return MagicMock()


@pytest.fixture
def mock_ta_service():
    s = MagicMock()
    s.analyze = AsyncMock(
        return_value=TechnicalAnalysisResult(
            symbol="BBCA.JK",
            current_price=Decimal("6050"),
            currency="IDR",
            data_points=60,
            rsi_14=Decimal("54.21"),
            rsi_status="neutral",
            sma_20=Decimal("6010"),
            sma_50=Decimal("5950"),
            price_vs_sma20="above",
            ma_trend="strong_bullish",
            support_20d=Decimal("5850"),
            resistance_20d=Decimal("6200"),
        )
    )
    return s


@pytest.fixture
def handlers(mock_market, mock_ta_service):
    return BotCommandHandlers(
        market_service=mock_market,
        allowed_ids=frozenset({1001}),
        ta_service=mock_ta_service,
    )


class TestTechnicalAnalysisCommands:
    @pytest.mark.asyncio
    async def test_ta_denied_user(self, handlers):
        update = make_mock_update(9999)
        ctx = make_mock_context(["BBCA.JK"])
        await handlers.cmd_ta(update, ctx)
        assert "Akses ditolak" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_ta_missing_args_shows_usage(self, handlers):
        update = make_mock_update(1001)
        ctx = make_mock_context([])
        await handlers.cmd_ta(update, ctx)
        assert "Penggunaan" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_ta_valid_symbol(self, handlers, mock_ta_service):
        update = make_mock_update(1001)
        loading_msg = AsyncMock()
        update.message.reply_text.return_value = loading_msg
        ctx = make_mock_context(["BBCA.JK"])

        await handlers.cmd_ta(update, ctx)

        mock_ta_service.analyze.assert_called_once_with("BBCA.JK")
        text = loading_msg.edit_text.call_args[0][0]
        assert "Analisis Teknikal: BBCA.JK" in text
        assert "RSI (14)" in text
        assert "MA20" in text
        assert "Bullish" in text

    @pytest.mark.asyncio
    async def test_ta_failed_result(self, handlers, mock_ta_service):
        mock_ta_service.analyze.return_value = TechnicalAnalysisResult(
            symbol="INVALID",
            error="quote_failed",
            error_message="Simbol tidak ditemukan",
        )
        update = make_mock_update(1001)
        loading_msg = AsyncMock()
        update.message.reply_text.return_value = loading_msg
        ctx = make_mock_context(["INVALID"])

        await handlers.cmd_ta(update, ctx)

        text = loading_msg.edit_text.call_args[0][0]
        assert "Gagal" in text
