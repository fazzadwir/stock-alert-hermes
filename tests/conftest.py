"""
MarketPulse — tests/conftest.py
Shared fixtures untuk semua tests.
TIDAK memerlukan Telegram token asli atau koneksi internet.
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.domain.market_schemas import DataStatus, InstrumentType, QuoteResult
from app.market_data.service import MarketDataService


# ─── Quote fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def sample_aapl_quote() -> QuoteResult:
    """Quote AAPL yang sukses."""
    return QuoteResult(
        symbol="AAPL",
        display_name="Apple Inc.",
        exchange="NASDAQ",
        instrument_type=InstrumentType.EQUITY,
        price=Decimal("182.50"),
        currency="USD",
        previous_close=Decimal("180.00"),
        price_change=Decimal("2.50"),
        price_change_pct=Decimal("1.39"),
        provider_timestamp=datetime(2026, 10, 10, 9, 0, 0, tzinfo=timezone.utc),
        fetch_timestamp=datetime(2026, 10, 10, 9, 0, 5, tzinfo=timezone.utc),
        source="yfinance",
        data_status=DataStatus.UNKNOWN,
    )


@pytest.fixture
def sample_bbca_quote() -> QuoteResult:
    """Quote BBCA.JK yang sukses."""
    return QuoteResult(
        symbol="BBCA.JK",
        display_name="Bank Central Asia Tbk",
        exchange="IDX",
        instrument_type=InstrumentType.EQUITY,
        price=Decimal("9875"),
        currency="IDR",
        previous_close=Decimal("9800"),
        price_change=Decimal("75"),
        price_change_pct=Decimal("0.77"),
        provider_timestamp=datetime(2026, 10, 10, 9, 30, 0, tzinfo=timezone.utc),
        fetch_timestamp=datetime(2026, 10, 10, 9, 30, 5, tzinfo=timezone.utc),
        source="yfinance",
        data_status=DataStatus.UNKNOWN,
    )


@pytest.fixture
def sample_gold_quote() -> QuoteResult:
    """Quote GC=F (Gold Futures) yang sukses."""
    return QuoteResult(
        symbol="GC=F",
        display_name="Gold Dec 26",
        exchange="COMEX",
        instrument_type=InstrumentType.FUTURES,
        price=Decimal("2650.40"),
        currency="USD",
        previous_close=Decimal("2640.00"),
        price_change=Decimal("10.40"),
        price_change_pct=Decimal("0.39"),
        provider_timestamp=datetime(2026, 10, 10, 9, 0, 0, tzinfo=timezone.utc),
        fetch_timestamp=datetime(2026, 10, 10, 9, 0, 5, tzinfo=timezone.utc),
        source="yfinance",
        data_status=DataStatus.UNKNOWN,
    )


@pytest.fixture
def invalid_symbol_quote() -> QuoteResult:
    """Quote untuk symbol yang tidak valid."""
    return QuoteResult(
        symbol="INVALID123XYZ",
        fetch_timestamp=datetime(2026, 10, 10, 9, 0, 0, tzinfo=timezone.utc),
        source="yfinance",
        data_status=DataStatus.UNAVAILABLE,
        error="invalid_symbol",
        error_message="Simbol tidak ditemukan.",
    )


@pytest.fixture
def timeout_quote() -> QuoteResult:
    """Quote yang gagal karena timeout."""
    return QuoteResult(
        symbol="AAPL",
        fetch_timestamp=datetime(2026, 10, 10, 9, 0, 0, tzinfo=timezone.utc),
        source="yfinance",
        data_status=DataStatus.UNAVAILABLE,
        error="provider_timeout",
        error_message="Timeout saat mengambil data.",
    )


# ─── Mock provider fixture ──────────────────────────────────────────────────

@pytest.fixture
def mock_provider(sample_aapl_quote):
    """Mock provider yang return AAPL quote secara default."""
    provider = MagicMock()
    provider.provider_name = "mock_provider"
    provider.get_quote = AsyncMock(return_value=sample_aapl_quote)
    provider.get_history = AsyncMock(return_value=None)
    return provider


@pytest.fixture
def mock_market_service(mock_provider):
    """MarketDataService yang menggunakan mock provider."""
    return MarketDataService(provider=mock_provider, cache_ttl_seconds=60)
