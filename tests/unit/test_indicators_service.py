"""
Unit tests untuk TechnicalAnalysisService.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.market_schemas import DataStatus, HistoricalCandles, QuoteResult
from app.indicators.service import TechnicalAnalysisService


@pytest.fixture
def mock_market():
    m = MagicMock()
    m._provider = MagicMock()
    m._provider.get_history = AsyncMock()
    m.get_quote = AsyncMock()
    return m


class TestTechnicalAnalysisService:
    @pytest.mark.asyncio
    async def test_analyze_successful(self, mock_market):
        mock_market.get_quote.return_value = QuoteResult(
            symbol="BBCA.JK",
            price=Decimal("6050"),
            currency="IDR",
            source="test",
            data_status=DataStatus.LAST_CLOSE,
        )

        # 30 hari data lilin
        closes = [Decimal(str(5800 + i * 10)) for i in range(30)]
        mock_market._provider.get_history.return_value = HistoricalCandles(
            symbol="BBCA.JK",
            closes=closes,
            highs=[c + Decimal("50") for c in closes],
            lows=[c - Decimal("50") for c in closes],
        )

        service = TechnicalAnalysisService(market_service=mock_market)
        res = await service.analyze("BBCA.JK")

        assert not res.is_failed
        assert res.symbol == "BBCA.JK"
        assert res.current_price == Decimal("6050")
        assert res.rsi_14 is not None
        assert res.sma_20 is not None

    @pytest.mark.asyncio
    async def test_analyze_insufficient_data(self, mock_market):
        mock_market.get_quote.return_value = QuoteResult(
            symbol="NEWCO",
            price=Decimal("100"),
            currency="USD",
            source="test",
            data_status=DataStatus.LAST_CLOSE,
        )

        # Hanya 5 hari
        mock_market._provider.get_history.return_value = HistoricalCandles(
            symbol="NEWCO",
            closes=[Decimal("100")] * 5,
        )

        service = TechnicalAnalysisService(market_service=mock_market)
        res = await service.analyze("NEWCO")

        assert res.is_failed
        assert res.error == "insufficient_data"

    @pytest.mark.asyncio
    async def test_analyze_quote_failed(self, mock_market):
        mock_market.get_quote.return_value = QuoteResult(
            symbol="INVALID",
            error="invalid_symbol",
            data_status=DataStatus.UNAVAILABLE,
            source="test",
        )

        service = TechnicalAnalysisService(market_service=mock_market)
        res = await service.analyze("INVALID")

        assert res.is_failed
        assert res.error == "quote_failed"
