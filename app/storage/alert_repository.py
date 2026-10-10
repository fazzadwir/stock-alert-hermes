"""
MarketPulse — app/storage/alert_repository.py
Repository untuk operasi data alert user (CRUD & trigger updates).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.storage.models import AlertCondition, AlertItem, AlertStatus

logger = logging.getLogger(__name__)


class AlertRepository:
    """Repository asynchronous untuk alert target harga & pergerakan pasar."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_alert(
        self,
        user_id: int,
        symbol: str,
        condition: str,
        target_value: Decimal,
        cooldown_minutes: int = 60,
        is_recurring: bool = False,
        note: Optional[str] = None,
    ) -> AlertItem:
        """Membuat alert baru untuk user."""
        symbol_upper = symbol.upper().strip()
        cond_str = condition.lower().strip()

        async with self._session_factory() as session:
            async with session.begin():
                alert = AlertItem(
                    user_id=user_id,
                    symbol=symbol_upper,
                    condition=cond_str,
                    target_value=target_value,
                    status=AlertStatus.ACTIVE.value,
                    cooldown_minutes=cooldown_minutes,
                    is_recurring=is_recurring,
                    note=note.strip() if note else None,
                )
                session.add(alert)
                await session.flush()
                await session.refresh(alert)
                logger.info(
                    "User %d membuat alert #%d: %s %s %s",
                    user_id, alert.id, symbol_upper, cond_str, target_value
                )
                return alert

    async def delete_alert(self, user_id: int, alert_id: int) -> bool:
        """Menghapus alert milik user berdasarkan ID."""
        async with self._session_factory() as session:
            async with session.begin():
                stmt = delete(AlertItem).where(
                    AlertItem.user_id == user_id,
                    AlertItem.id == alert_id,
                )
                result = await session.execute(stmt)
                deleted = result.rowcount > 0
                if deleted:
                    logger.info("User %d menghapus alert #%d", user_id, alert_id)
                return deleted

    async def get_user_alerts(
        self,
        user_id: int,
        status: Optional[str] = None,
    ) -> list[AlertItem]:
        """Mengambil daftar alert milik user."""
        async with self._session_factory() as session:
            stmt = select(AlertItem).where(AlertItem.user_id == user_id)
            if status:
                stmt = stmt.where(AlertItem.status == status)
            stmt = stmt.order_by(AlertItem.created_at.desc())
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_user_active_alerts(self, user_id: int) -> int:
        """Menghitung total alert aktif milik user."""
        async with self._session_factory() as session:
            stmt = select(func.count(AlertItem.id)).where(
                AlertItem.user_id == user_id,
                AlertItem.status == AlertStatus.ACTIVE.value,
            )
            result = await session.execute(stmt)
            return result.scalar_one() or 0

    async def get_all_active_alerts(self) -> list[AlertItem]:
        """Mengambil seluruh alert aktif dari semua user untuk dievaluasi oleh worker."""
        async with self._session_factory() as session:
            stmt = (
                select(AlertItem)
                .where(AlertItem.status == AlertStatus.ACTIVE.value)
                .order_by(AlertItem.symbol.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def mark_triggered(
        self,
        alert_id: int,
        triggered_at: datetime,
        is_recurring: bool = False,
    ) -> None:
        """
        Memperbarui status alert setelah terpicu.
        Jika is_recurring False, status diubah menjadi TRIGGERED.
        """
        new_status = AlertStatus.ACTIVE.value if is_recurring else AlertStatus.TRIGGERED.value
        async with self._session_factory() as session:
            async with session.begin():
                stmt = (
                    update(AlertItem)
                    .where(AlertItem.id == alert_id)
                    .values(
                        status=new_status,
                        last_triggered_at=triggered_at,
                    )
                )
                await session.execute(stmt)
                logger.info("Alert #%d dimark triggered (status=%s)", alert_id, new_status)
