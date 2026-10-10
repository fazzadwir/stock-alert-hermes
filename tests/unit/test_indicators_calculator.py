"""
Unit tests untuk kalkulator matematika indikator teknikal (RSI, SMA, Cross, S/R).
Semua pengujian menggunakan dataset deterministik tanpa koneksi internet.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.indicators.calculator import (
    analyze_trend,
    calculate_rsi,
    calculate_sma,
    calculate_support_resistance,
    detect_crossover,
)


class TestCalculateSMA:
    def test_sma_exact_values(self):
        prices = [Decimal(x) for x in ["10", "20", "30", "40", "50"]]
        # 5-period SMA: (10+20+30+40+50)/5 = 30
        assert calculate_sma(prices, 5) == Decimal("30.00")
        # 3-period SMA: (30+40+50)/3 = 40
        assert calculate_sma(prices, 3) == Decimal("40.00")

    def test_sma_insufficient_data_returns_none(self):
        prices = [Decimal(x) for x in ["10", "20"]]
        assert calculate_sma(prices, 5) is None

    def test_sma_empty_returns_none(self):
        assert calculate_sma([], 5) is None


class TestCalculateRSI:
    def test_rsi_all_gains_returns_100(self):
        # Harga naik terus setiap hari
        prices = [Decimal(str(100 + i * 2)) for i in range(20)]
        rsi = calculate_rsi(prices, period=14)
        assert rsi == Decimal("100.00")

    def test_rsi_all_losses_returns_0(self):
        # Harga turun terus setiap hari
        prices = [Decimal(str(200 - i * 2)) for i in range(20)]
        rsi = calculate_rsi(prices, period=14)
        assert rsi == Decimal("0.00")

    def test_rsi_insufficient_data_returns_none(self):
        prices = [Decimal("100"), Decimal("102"), Decimal("101")]
        assert calculate_rsi(prices, period=14) is None

    def test_rsi_mixed_market(self):
        # 15 data penutupan bergantian naik dan turun
        prices = [
            Decimal("44.34"), Decimal("44.09"), Decimal("44.15"), Decimal("43.61"),
            Decimal("44.33"), Decimal("44.83"), Decimal("45.10"), Decimal("45.42"),
            Decimal("45.84"), Decimal("46.08"), Decimal("45.89"), Decimal("46.03"),
            Decimal("45.61"), Decimal("46.28"), Decimal("46.28"), Decimal("46.00"),
        ]
        rsi = calculate_rsi(prices, period=14)
        assert rsi is not None
        assert Decimal("30") < rsi < Decimal("80")


class TestDetectCrossover:
    def test_golden_cross_detection(self):
        # Buat dataset di mana MA5 memotong ke atas MA10
        # Periode sebelumnya: short <= long. Periode sekarang: short > long.
        prices = [Decimal("100")] * 12
        # Harga melonjak drastis di akhir
        prices.append(Decimal("150"))
        cross = detect_crossover(prices, short_period=3, long_period=5)
        assert cross == "golden_cross"

    def test_death_cross_detection(self):
        # Buat dataset di mana MA pendek turun menembus MA panjang
        prices = [Decimal("100")] * 12
        prices.append(Decimal("40"))
        cross = detect_crossover(prices, short_period=3, long_period=5)
        assert cross == "death_cross"

    def test_no_crossover(self):
        prices = [Decimal("100")] * 15
        assert detect_crossover(prices, short_period=3, long_period=5) is None


class TestSupportResistance:
    def test_support_and_resistance(self):
        highs = [Decimal(str(x)) for x in range(100, 125)]  # max is 124
        lows = [Decimal(str(x)) for x in range(80, 105)]    # min in last 20 is 85
        sup, res = calculate_support_resistance(highs, lows, period=20)
        assert res == Decimal("124.00")
        assert sup == Decimal("85.00")


class TestAnalyzeTrend:
    def test_strong_bullish(self):
        trend = analyze_trend(Decimal("110"), sma_20=Decimal("105"), sma_50=Decimal("100"))
        assert trend == "strong_bullish"

    def test_strong_bearish(self):
        trend = analyze_trend(Decimal("90"), sma_20=Decimal("95"), sma_50=Decimal("100"))
        assert trend == "strong_bearish"

    def test_neutral_when_no_sma(self):
        assert analyze_trend(Decimal("100"), None, None) == "neutral"
