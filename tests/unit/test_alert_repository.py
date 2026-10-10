"""
Unit tests untuk AlertRepository.
Menggunakan in-memory SQLite (aiosqlite).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.storage.models import AlertCondition, AlertStatus, Base
from app.storage.alert_repository import AlertRepository


@pytest_asyncio.fixture
async def alert_repo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    repo = AlertRepository(session_factory=session_factory)
    yield repo
    await engine.dispose()


class TestAlertRepository:
    @pytest.mark.asyncio
    async def test_create_and_get_alert(self, alert_repo: AlertRepository):
        alert = await alert_repo.create_alert(
            user_id=101,
            symbol="BBCA.JK",
            condition="above",
            target_value=Decimal("6200.00"),
            cooldown_minutes=30,
            note="Target jual",
        )
        assert alert.id is not None
        assert alert.user_id == 101
        assert alert.symbol == "BBCA.JK"
        assert alert.condition == "above"
        assert alert.target_value == Decimal("6200.00")
        assert alert.status == AlertStatus.ACTIVE.value
        assert alert.cooldown_minutes == 30
        assert alert.note == "Target jual"

        alerts = await alert_repo.get_user_alerts(101)
        assert len(alerts) == 1
        assert alerts[0].id == alert.id

    @pytest.mark.asyncio
    async def test_count_user_active_alerts(self, alert_repo: AlertRepository):
        assert await alert_repo.count_user_active_alerts(101) == 0

        a1 = await alert_repo.create_alert(101, "AAPL", "above", Decimal("220"))
        a2 = await alert_repo.create_alert(101, "BBCA.JK", "below", Decimal("5900"))
        assert await alert_repo.count_user_active_alerts(101) == 2

        # Trigger one
        await alert_repo.mark_triggered(a1.id, datetime.now(timezone.utc), is_recurring=False)
        assert await alert_repo.count_user_active_alerts(101) == 1

    @pytest.mark.asyncio
    async def test_get_all_active_alerts_across_users(self, alert_repo: AlertRepository):
        await alert_repo.create_alert(101, "AAPL", "above", Decimal("220"))
        await alert_repo.create_alert(102, "BBCA.JK", "below", Decimal("5900"))

        all_active = await alert_repo.get_all_active_alerts()
        assert len(all_active) == 2

    @pytest.mark.asyncio
    async def test_mark_triggered_one_time_vs_recurring(self, alert_repo: AlertRepository):
        a_once = await alert_repo.create_alert(101, "AAPL", "above", Decimal("220"), is_recurring=False)
        a_rec = await alert_repo.create_alert(101, "BBCA.JK", "below", Decimal("5900"), is_recurring=True)

        now = datetime.now(timezone.utc)
        await alert_repo.mark_triggered(a_once.id, now, is_recurring=False)
        await alert_repo.mark_triggered(a_rec.id, now, is_recurring=True)

        alerts = await alert_repo.get_user_alerts(101)
        alert_map = {a.id: a for a in alerts}

        assert alert_map[a_once.id].status == AlertStatus.TRIGGERED.value
        assert alert_map[a_once.id].last_triggered_at is not None

        assert alert_map[a_rec.id].status == AlertStatus.ACTIVE.value
        assert alert_map[a_rec.id].last_triggered_at is not None

    @pytest.mark.asyncio
    async def test_delete_alert(self, alert_repo: AlertRepository):
        a = await alert_repo.create_alert(101, "AAPL", "above", Decimal("220"))
        # User 102 should not be able to delete User 101's alert
        assert await alert_repo.delete_alert(102, a.id) is False

        # User 101 deletes own alert
        assert await alert_repo.delete_alert(101, a.id) is True
        assert len(await alert_repo.get_user_alerts(101)) == 0
