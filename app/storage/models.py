"""
MarketPulse — app/storage/models.py
Model SQLAlchemy deklaratif untuk penyimpanan data watchlist & alerts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base deklaratif SQLAlchemy untuk semua model MarketPulse."""
    pass


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
