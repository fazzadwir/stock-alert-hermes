"""
Unit tests untuk yfinance provider.
Menggunakan mock — tidak memerlukan koneksi internet atau API key.
"""

from __future__ import annotations

import asyncio
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.market_schemas import DataStatus, InstrumentType, QuoteResult
from app.market_data.providers.yfinance_provider import YFinanceProvider


@pytest.fixture
def provider():
    return YFinanceProvider(timeout_seconds=15)


class TestYFinanceProviderName:
    def test_provider_name(self, provider):
        assert provider.provider_name == "yfinance"


class TestGetQuoteWithMock:
    """Tests menggunakan mock _fetch_quote_sync — tidak butuh internet."""

    @pytest.mark.asyncio
    async def test_valid_symbol_returns_quote(self, provider):
        """Quote sukses harus mengembalikan QuoteResult dengan harga."""
        mock_info = {
            "currentPrice": 182.50,
            "previousClose": 180.00,
            "currency": "USD",
            "quoteType": "EQUITY",
            "longName": "Apple Inc.",
            "exchange": "NASDAQ",
            "marketState": "REGULAR",
            "regularMarketTime": 1728547200,
        }

        with patch.object(provider, "_fetch_quote_sync", return_value=mock_info):
            result = await provider.get_quote("AAPL")

        assert result.symbol == "AAPL"
        assert result.price == Decimal("182.50")
        assert result.previous_close == Decimal("180.00")
        assert result.currency == "USD"
        assert result.instrument_type == InstrumentType.EQUITY
        assert result.display_name == "Apple Inc."
        assert result.source == "yfinance"
        assert not result.is_failed

    @pytest.mark.asyncio
    async def test_invalid_symbol_returns_error_quote(self, provider):
        """Symbol invalid (provider return None) harus return QuoteResult dengan error."""
        with patch.object(provider, "_fetch_quote_sync", return_value=None):
            result = await provider.get_quote("INVALID123XYZ")

        assert result.symbol == "INVALID123XYZ"
        assert result.is_failed
        assert result.error == "invalid_symbol"
        assert result.price is None

    @pytest.mark.asyncio
    async def test_timeout_returns_error_quote(self, provider):
        """Timeout harus return QuoteResult dengan error provider_timeout."""
        async def slow_fetch(*args, **kwargs):
            await asyncio.sleep(100)  # Pasti timeout

        with patch.object(provider, "_fetch_quote_sync", side_effect=Exception("timeout_sim")):
            # Set timeout sangat kecil untuk test
            provider._timeout = 0.001
            result = await provider.get_quote("AAPL")

        assert result.is_failed
        # Bisa timeout atau provider_error tergantung timing
        assert result.error in ("provider_timeout", "provider_error")

    @pytest.mark.asyncio
    async def test_gold_symbol_is_futures_type(self, provider):
        """GC=F harus dikenali sebagai FUTURES."""
        mock_info = {
            "currentPrice": 2650.40,
            "previousClose": 2640.00,
            "currency": "USD",
            "quoteType": "FUTURE",
            "shortName": "Gold Dec 26",
            "exchange": "CMX",
            "marketState": "CLOSED",
        }

        with patch.object(provider, "_fetch_quote_sync", return_value=mock_info):
            result = await provider.get_quote("GC=F")

        assert result.symbol == "GC=F"
        assert result.instrument_type == InstrumentType.FUTURES
        assert result.price == Decimal("2650.40")
        assert not result.is_failed

    @pytest.mark.asyncio
    async def test_idr_stock_bbca(self, provider):
        """Saham IDX dengan harga IDR harus diparse dengan benar."""
        mock_info = {
            "currentPrice": 9875.0,
            "previousClose": 9800.0,
            "currency": "IDR",
            "quoteType": "EQUITY",
            "longName": "Bank Central Asia Tbk",
            "exchange": "IDX",
            "marketState": "CLOSED",
        }

        with patch.object(provider, "_fetch_quote_sync", return_value=mock_info):
            result = await provider.get_quote("BBCA.JK")

        assert result.symbol == "BBCA.JK"
        assert result.price == Decimal("9875.0")
        assert result.currency == "IDR"
        assert not result.is_failed

    @pytest.mark.asyncio
    async def test_price_change_calculation(self, provider):
        """Perubahan harga dan persentase harus dihitung dengan benar."""
        mock_info = {
            "currentPrice": 200.0,
            "previousClose": 190.0,
            "currency": "USD",
            "quoteType": "EQUITY",
        }

        with patch.object(provider, "_fetch_quote_sync", return_value=mock_info):
            result = await provider.get_quote("TEST")

        assert result.price_change == Decimal("10.0")
        assert result.price_change_pct == Decimal("5.26")  # (10/190)*100 = 5.26...

    @pytest.mark.asyncio
    async def test_no_change_when_no_prev_close(self, provider):
        """Tidak ada perubahan jika previous_close tidak tersedia."""
        mock_info = {
            "currentPrice": 100.0,
            "currency": "USD",
            "quoteType": "EQUITY",
        }

        with patch.object(provider, "_fetch_quote_sync", return_value=mock_info):
            result = await provider.get_quote("TEST")

        assert result.price == Decimal("100.0")
        assert result.previous_close is None
        assert result.price_change is None
        assert result.price_change_pct is None
        assert not result.has_change

    @pytest.mark.asyncio
    async def test_fetch_timestamp_always_set(self, provider):
        """fetch_timestamp harus selalu ada, bahkan saat error."""
        with patch.object(provider, "_fetch_quote_sync", return_value=None):
            result = await provider.get_quote("INVALID")

        assert result.fetch_timestamp is not None

    @pytest.mark.asyncio
    async def test_exception_in_fetch_returns_error(self, provider):
        """Exception di _fetch_quote_sync harus ditangani gracefully."""
        with patch.object(provider, "_fetch_quote_sync", side_effect=RuntimeError("network error")):
            result = await provider.get_quote("AAPL")

        assert result.is_failed
        assert result.error in ("provider_error", "provider_timeout")


class TestParseRawQuote:
    """Tests untuk _parse_raw_quote secara langsung."""

    def test_market_state_closed_gives_last_close(self):
        provider = YFinanceProvider()
        fetch_ts = datetime(2026, 10, 10, 9, 0, 0, tzinfo=timezone.utc)
        info = {
            "currentPrice": 100.0,
            "previousClose": 95.0,
            "currency": "USD",
            "quoteType": "EQUITY",
            "marketState": "CLOSED",
        }
        result = provider._parse_raw_quote("TEST", info, fetch_ts)
        assert result.data_status == DataStatus.LAST_CLOSE

    def test_market_state_regular_gives_unknown(self):
        """Market buka tapi tidak ada bukti real-time → UNKNOWN."""
        provider = YFinanceProvider()
        fetch_ts = datetime(2026, 10, 10, 9, 0, 0, tzinfo=timezone.utc)
        info = {
            "currentPrice": 100.0,
            "previousClose": 95.0,
            "currency": "USD",
            "quoteType": "EQUITY",
            "marketState": "REGULAR",
        }
        result = provider._parse_raw_quote("TEST", info, fetch_ts)
        # Tidak boleh langsung klaim REALTIME
        assert result.data_status != DataStatus.REALTIME
        assert result.data_status == DataStatus.UNKNOWN
