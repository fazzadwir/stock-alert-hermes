"""
MarketPulse — app/indicators/service.py
Service untuk orkestrasi pengambilan data historis dan analisis teknikal.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from app.domain.market_schemas import TechnicalAnalysisResult
from app.indicators.calculator import (
    analyze_trend,
    calculate_rsi,
    calculate_sma,
    calculate_support_resistance,
    detect_crossover,
)
from app.market_data.service import MarketDataService

logger = logging.getLogger(__name__)


class TechnicalAnalysisService:
    """Service analisis teknikal pasar."""

    def __init__(self, market_service: MarketDataService) -> None:
        self._market = market_service

    async def analyze(self, symbol: str) -> TechnicalAnalysisResult:
        """
        Melakukan analisis teknikal komprehensif (RSI, MA20/50, Crossover, S/R).
        Selalu mengembalikan TechnicalAnalysisResult (tidak raise exception).
        """
        symbol_upper = symbol.upper().strip()

        # 1. Ambil quote terkini
        quote = await self._market.get_quote(symbol_upper)
        if quote.is_failed or not quote.has_price or quote.price is None:
            return TechnicalAnalysisResult(
                symbol=symbol_upper,
                error="quote_failed",
                error_message=f"Simbol '{symbol_upper}' tidak ditemukan atau data harga tidak tersedia.",
            )

        # 2. Ambil data candle historis 6 bulan terakhir
        try:
            candles = await self._market._provider.get_history(symbol_upper, period="6mo", interval="1d")
        except Exception as exc:
            logger.error("Error mengambil riwayat lilin untuk %s: %s", symbol_upper, exc)
            candles = None

        if candles is None or candles.count < 15:
            count = candles.count if candles else 0
            return TechnicalAnalysisResult(
                symbol=symbol_upper,
                current_price=quote.price,
                currency=quote.currency,
                data_points=count,
                error="insufficient_data",
                error_message=f"Data historis tidak mencukupi untuk analisis (tersedia {count} hari, butuh minimal 15 hari).",
            )

        closes = candles.closes
        highs = candles.highs or closes
        lows = candles.lows or closes

        # 3. Hitung indikator
        rsi = calculate_rsi(closes, period=14)
        rsi_status = "neutral"
        if rsi is not None:
            if rsi >= Decimal("70"):
                rsi_status = "overbought"
            elif rsi <= Decimal("30"):
                rsi_status = "oversold"

        sma_20 = calculate_sma(closes, period=20)
        sma_50 = calculate_sma(closes, period=50)

        price_vs_sma20 = None
        if sma_20 is not None:
            price_vs_sma20 = "above" if quote.price >= sma_20 else "below"

        trend = analyze_trend(quote.price, sma_20, sma_50)
        crossover = detect_crossover(closes, short_period=20, long_period=50)
        support, resistance = calculate_support_resistance(highs, lows, period=20)

        logger.info(
            "Analisis teknikal selesai untuk %s: Price=%s, RSI=%s, SMA20=%s, SMA50=%s, Trend=%s",
            symbol_upper, quote.price, rsi, sma_20, sma_50, trend
        )

        return TechnicalAnalysisResult(
            symbol=symbol_upper,
            current_price=quote.price,
            currency=quote.currency,
            data_points=candles.count,
            rsi_14=rsi,
            rsi_status=rsi_status,
            sma_20=sma_20,
            sma_50=sma_50,
            price_vs_sma20=price_vs_sma20,
            ma_trend=trend,
            ma_crossover=crossover,
            support_20d=support,
            resistance_20d=resistance,
        )
