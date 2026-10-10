"""
Unit tests untuk AlertEngine, evaluasi kondisi, dan cooldown control.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.alerts.engine import AlertEngine, evaluate_condition, is_in_cooldown
from app.domain.market_schemas import DataStatus, InstrumentType, QuoteResult
from app.storage.models import AlertCondition, AlertItem, AlertStatus


def make_quote(
    symbol: str,
    price: Decimal | None,
    previous_close: Decimal | None = None,
    price_change: Decimal | None = None,
    price_change_pct: Decimal | None = None,
) -> QuoteResult:
    return QuoteResult(
        symbol=symbol,
        price=price,
        previous_close=previous_close,
        price_change=price_change,
        price_change_pct=price_change_pct,
        currency="IDR",
        source="test",
        data_status=DataStatus.LAST_CLOSE if price else DataStatus.UNAVAILABLE,
    )


class TestEvaluateCondition:
    def test_above_triggered_when_price_higher(self):
        q = make_quote("BBCA.JK", Decimal("6250"))
        assert evaluate_condition("above", Decimal("6200"), q) is True

    def test_above_triggered_when_price_equal(self):
        q = make_quote("BBCA.JK", Decimal("6200"))
        assert evaluate_condition("above", Decimal("6200"), q) is True

    def test_above_not_triggered_when_price_lower(self):
        q = make_quote("BBCA.JK", Decimal("6150"))
        assert evaluate_condition("above", Decimal("6200"), q) is False

    def test_below_triggered_when_price_lower(self):
        q = make_quote("BBCA.JK", Decimal("5950"))
        assert evaluate_condition("below", Decimal("6000"), q) is True

    def test_below_not_triggered_when_price_higher(self):
        q = make_quote("BBCA.JK", Decimal("6050"))
        assert evaluate_condition("below", Decimal("6000"), q) is False

    def test_pct_up_condition(self):
        q = make_quote(
            "AAPL",
            price=Decimal("105"),
            previous_close=Decimal("100"),
            price_change=Decimal("5"),
            price_change_pct=Decimal("5.0"),
        )
        assert evaluate_condition("pct_up", Decimal("3.0"), q) is True
        assert evaluate_condition("pct_up", Decimal("6.0"), q) is False

    def test_pct_down_condition(self):
        q = make_quote(
            "AAPL",
            price=Decimal("95"),
            previous_close=Decimal("100"),
            price_change=Decimal("-5"),
            price_change_pct=Decimal("-5.0"),
        )
        assert evaluate_condition("pct_down", Decimal("3.0"), q) is True  # down 5% >= down 3%
        assert evaluate_condition("pct_down", Decimal("7.0"), q) is False

    def test_no_price_returns_false(self):
        q = make_quote("TEST", None)
        assert evaluate_condition("above", Decimal("100"), q) is False
        assert evaluate_condition("below", Decimal("100"), q) is False


class TestCooldown:
    def test_no_previous_trigger_not_in_cooldown(self):
        alert = AlertItem(
            id=1, user_id=1, symbol="TEST", condition="above", target_value=Decimal("100"),
            cooldown_minutes=60, last_triggered_at=None,
        )
        now = datetime.now(timezone.utc)
        assert is_in_cooldown(alert, now) is False

    def test_recently_triggered_is_in_cooldown(self):
        now = datetime.now(timezone.utc)
        alert = AlertItem(
            id=1, user_id=1, symbol="TEST", condition="above", target_value=Decimal("100"),
            cooldown_minutes=60, last_triggered_at=now - timedelta(minutes=10),
        )
        assert is_in_cooldown(alert, now) is True

    def test_cooldown_expired(self):
        now = datetime.now(timezone.utc)
        alert = AlertItem(
            id=1, user_id=1, symbol="TEST", condition="above", target_value=Decimal("100"),
            cooldown_minutes=60, last_triggered_at=now - timedelta(minutes=61),
        )
        assert is_in_cooldown(alert, now) is False


class TestAlertEngineCycle:
    @pytest.mark.asyncio
    async def test_check_alerts_triggers_and_calls_notify(self):
        alert = AlertItem(
            id=10,
            user_id=1001,
            symbol="BBCA.JK",
            condition="above",
            target_value=Decimal("6000"),
            status=AlertStatus.ACTIVE.value,
            cooldown_minutes=60,
            is_recurring=False,
            last_triggered_at=None,
        )

        repo = MagicMock()
        repo.get_all_active_alerts = AsyncMock(return_value=[alert])
        repo.mark_triggered = AsyncMock()

        market = MagicMock()
        market.get_quote = AsyncMock(return_value=make_quote("BBCA.JK", Decimal("6050")))

        callback = AsyncMock()

        engine = AlertEngine(
            alert_repo=repo,
            market_service=market,
            notify_callback=callback,
        )

        triggered = await engine.check_alerts_once()

        assert len(triggered) == 1
        assert triggered[0][0].id == 10
        repo.mark_triggered.assert_called_once()
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_alert_not_triggered_if_condition_not_met(self):
        alert = AlertItem(
            id=10,
            user_id=1001,
            symbol="BBCA.JK",
            condition="above",
            target_value=Decimal("7000"),  # price is lower
            status=AlertStatus.ACTIVE.value,
            cooldown_minutes=60,
            is_recurring=False,
            last_triggered_at=None,
        )

        repo = MagicMock()
        repo.get_all_active_alerts = AsyncMock(return_value=[alert])
        repo.mark_triggered = AsyncMock()

        market = MagicMock()
        market.get_quote = AsyncMock(return_value=make_quote("BBCA.JK", Decimal("6050")))

        callback = AsyncMock()

        engine = AlertEngine(
            alert_repo=repo,
            market_service=market,
            notify_callback=callback,
        )

        triggered = await engine.check_alerts_once()

        assert len(triggered) == 0
        repo.mark_triggered.assert_not_called()
        callback.assert_not_called()
