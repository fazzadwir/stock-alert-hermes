"""
MarketPulse — app/storage/models.py
Model SQLAlchemy deklaratif untuk penyimpanan data watchlist & alerts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from enum import Enum
from decimal import Decimal
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base deklaratif SQLAlchemy untuk semua model MarketPulse."""
    pass


class AlertCondition(str, Enum):
    """Kondisi pemicu alert harga."""
    ABOVE = "above"       # Harga naik melampaui target
    BELOW = "below"       # Harga turun melampaui target
    PCT_UP = "pct_up"     # Persentase kenaikan harian (%)
    PCT_DOWN = "pct_down" # Persentase penurunan harian (%)


class AlertStatus(str, Enum):
    """Status lifecycle alert."""
    ACTIVE = "active"         # Menunggu kondisi terpenuhi
    TRIGGERED = "triggered"   # Sudah terpicu
    DISABLED = "disabled"     # Dinonaktifkan manual


class WatchlistItem(Base):
    """Item dalam watchlist saham/komoditas milik user."""

    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "symbol", name="uq_user_symbol"),
    )

    def __repr__(self) -> str:
        return f"<WatchlistItem(user_id={self.user_id}, symbol='{self.symbol}', note='{self.note}')>"


class AlertItem(Base):
    """Definisi alert harga atau pergerakan pasar milik user."""

    __tablename__ = "alert_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    condition: Mapped[str] = mapped_column(String(16), nullable=False)  # AlertCondition value
    target_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=AlertStatus.ACTIVE.value, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AlertItem(id={self.id}, user_id={self.user_id}, symbol='{self.symbol}', "
            f"condition='{self.condition}', target={self.target_value}, status='{self.status}')>"
        )

