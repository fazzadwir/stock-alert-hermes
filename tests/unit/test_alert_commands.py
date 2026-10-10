"""
Unit tests untuk command Telegram alert (/alert, /alerts, /delalert).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.commands import BotCommandHandlers
from app.domain.market_schemas import DataStatus, QuoteResult
from app.storage.models import AlertItem, AlertStatus


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
    m.get_quote = AsyncMock(
        return_value=QuoteResult(
            symbol="BBCA.JK",
            price=Decimal("6050"),
            currency="IDR",
            source="test",
            data_status=DataStatus.LAST_CLOSE,
        )
    )
    return m


@pytest.fixture
def mock_alert_repo():
    r = MagicMock()
    r.count_user_active_alerts = AsyncMock(return_value=0)
    r.create_alert = AsyncMock(
        return_value=AlertItem(
            id=1,
            user_id=1001,
            symbol="BBCA.JK",
            condition="above",
            target_value=Decimal("6200"),
            status=AlertStatus.ACTIVE.value,
        )
    )
    r.get_user_alerts = AsyncMock(return_value=[])
    r.delete_alert = AsyncMock(return_value=True)
    return r


@pytest.fixture
def handlers(mock_market, mock_alert_repo):
    return BotCommandHandlers(
        market_service=mock_market,
        allowed_ids=frozenset({1001}),
        alert_repo=mock_alert_repo,
        max_active_alerts=5,
    )


class TestAlertCommands:
    @pytest.mark.asyncio
    async def test_alert_denied_user(self, handlers):
        update = make_mock_update(9999)
        ctx = make_mock_context(["BBCA.JK", "above", "6200"])
        await handlers.cmd_alert(update, ctx)
        assert "Akses ditolak" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_alert_missing_args(self, handlers):
        update = make_mock_update(1001)
        ctx = make_mock_context(["BBCA.JK"])
        await handlers.cmd_alert(update, ctx)
        assert "Penggunaan" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_alert_invalid_condition(self, handlers):
        update = make_mock_update(1001)
        ctx = make_mock_context(["BBCA.JK", "higher", "6200"])
        await handlers.cmd_alert(update, ctx)
        assert "above" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_alert_invalid_target_price(self, handlers):
        update = make_mock_update(1001)
        ctx = make_mock_context(["BBCA.JK", "above", "abc"])
        await handlers.cmd_alert(update, ctx)
        assert "tidak valid" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_alert_limit_reached(self, handlers, mock_alert_repo):
        mock_alert_repo.count_user_active_alerts.return_value = 5  # limit is 5
        update = make_mock_update(1001)
        ctx = make_mock_context(["BBCA.JK", "above", "6200"])
        await handlers.cmd_alert(update, ctx)
        assert "mencapai batas maksimal" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_alert_create_success(self, handlers, mock_alert_repo):
        update = make_mock_update(1001)
        loading_msg = AsyncMock()
        update.message.reply_text.return_value = loading_msg
        ctx = make_mock_context(["BBCA.JK", "above", "6200", "Target", "Take", "Profit"])

        await handlers.cmd_alert(update, ctx)
        mock_alert_repo.create_alert.assert_called_once_with(
            user_id=1001,
            symbol="BBCA.JK",
            condition="above",
            target_value=Decimal("6200"),
            note="Target Take Profit",
        )
        assert "Berhasil Dibuat" in loading_msg.edit_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_alerts_empty(self, handlers, mock_alert_repo):
        mock_alert_repo.get_user_alerts.return_value = []
        update = make_mock_update(1001)
        ctx = make_mock_context()
        await handlers.cmd_alerts(update, ctx)
        assert "Belum Ada Alert" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_alerts_list(self, handlers, mock_alert_repo):
        alert = AlertItem(
            id=5, user_id=1001, symbol="AAPL", condition="below", target_value=Decimal("200"),
            status=AlertStatus.ACTIVE.value,
        )
        mock_alert_repo.get_user_alerts.return_value = [alert]
        update = make_mock_update(1001)
        ctx = make_mock_context()
        await handlers.cmd_alerts(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "#5" in text
        assert "AAPL" in text

    @pytest.mark.asyncio
    async def test_delalert_no_args(self, handlers):
        update = make_mock_update(1001)
        ctx = make_mock_context([])
        await handlers.cmd_delalert(update, ctx)
        assert "Penggunaan" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_delalert_invalid_id(self, handlers):
        update = make_mock_update(1001)
        ctx = make_mock_context(["not_a_number"])
        await handlers.cmd_delalert(update, ctx)
        assert "angka bulat" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_delalert_success(self, handlers, mock_alert_repo):
        mock_alert_repo.delete_alert.return_value = True
        update = make_mock_update(1001)
        ctx = make_mock_context(["1"])
        await handlers.cmd_delalert(update, ctx)
        mock_alert_repo.delete_alert.assert_called_once_with(1001, 1)
        assert "berhasil dihapus" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_delalert_not_found(self, handlers, mock_alert_repo):
        mock_alert_repo.delete_alert.return_value = False
        update = make_mock_update(1001)
        ctx = make_mock_context(["999"])
        await handlers.cmd_delalert(update, ctx)
        assert "tidak ditemukan" in update.message.reply_text.call_args[0][0]
