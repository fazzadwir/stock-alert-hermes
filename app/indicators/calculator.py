"""
MarketPulse — app/indicators/calculator.py
Fungsi kalkulasi indikator teknikal murni Python (RSI, SMA, Crossover, Support/Resistance).
Semua perhitungan menggunakan Decimal untuk ketelitian finansial.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


def calculate_sma(closes: list[Decimal], period: int) -> Optional[Decimal]:
    """
    Hitung Simple Moving Average (SMA) untuk N periode terakhir.
    Returns None jika data penutupan kurang dari periode.
    """
    if not closes or len(closes) < period or period <= 0:
        return None

    subset = closes[-period:]
    total = sum(subset)
    sma = total / Decimal(str(period))
    return sma.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_rsi(closes: list[Decimal], period: int = 14) -> Optional[Decimal]:
    """
    Hitung Relative Strength Index (RSI) dengan metode smoothed Wilder.
    Returns None jika data penutupan kurang dari period + 1.
    """
    if not closes or len(closes) < period + 1 or period <= 0:
        return None

    # Hitung perubahan harga (delta)
    deltas: list[Decimal] = []
    for i in range(1, len(closes)):
        deltas.append(closes[i] - closes[i - 1])

    # Inisialisasi gain dan loss pertama (simple average)
    gains: list[Decimal] = [d if d > 0 else Decimal("0") for d in deltas[:period]]
    losses: list[Decimal] = [-d if d < 0 else Decimal("0") for d in deltas[:period]]

    p_dec = Decimal(str(period))
    avg_gain = sum(gains) / p_dec
    avg_loss = sum(losses) / p_dec

    # Wilder's Smoothing untuk data selanjutnya
    for d in deltas[period:]:
        gain = d if d > 0 else Decimal("0")
        loss = -d if d < 0 else Decimal("0")
        avg_gain = ((avg_gain * (p_dec - 1)) + gain) / p_dec
        avg_loss = ((avg_loss * (p_dec - 1)) + loss) / p_dec

    # Tangani kondisi khusus
    if avg_loss == Decimal("0"):
        return Decimal("100.00")
    if avg_gain == Decimal("0"):
        return Decimal("0.00")

    rs = avg_gain / avg_loss
    rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))
    return rsi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def detect_crossover(
    closes: list[Decimal],
    short_period: int = 20,
    long_period: int = 50,
) -> Optional[str]:
    """
    Deteksi Moving Average Crossover (Golden Cross / Death Cross).
    Returns:
        "golden_cross": MA pendek baru saja memotong ke atas MA panjang
        "death_cross": MA pendek baru saja memotong ke bawah MA panjang
        None: Tidak ada persilangan baru
    """
    if len(closes) < long_period + 1:
        return None

    sma_short_now = calculate_sma(closes, short_period)
    sma_long_now = calculate_sma(closes, long_period)
    sma_short_prev = calculate_sma(closes[:-1], short_period)
    sma_long_prev = calculate_sma(closes[:-1], long_period)

    if (
        sma_short_now is None
        or sma_long_now is None
        or sma_short_prev is None
        or sma_long_prev is None
    ):
        return None

    # Golden cross: MA pendek naik menembus MA panjang
    if sma_short_prev <= sma_long_prev and sma_short_now > sma_long_now:
        return "golden_cross"

    # Death cross: MA pendek turun menembus MA panjang
    if sma_short_prev >= sma_long_prev and sma_short_now < sma_long_now:
        return "death_cross"

    return None


def calculate_support_resistance(
    highs: list[Decimal],
    lows: list[Decimal],
    period: int = 20,
) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Hitung Support dan Resistance berdasarkan harga High/Low N hari terakhir.
    Returns: (support, resistance)
    """
    if not highs or not lows or len(highs) < period or len(lows) < period:
        return None, None

    res = max(highs[-period:])
    sup = min(lows[-period:])
    return sup.quantize(Decimal("0.01")), res.quantize(Decimal("0.01"))


def analyze_trend(
    current_price: Decimal,
    sma_20: Optional[Decimal],
    sma_50: Optional[Decimal],
) -> str:
    """Analisis arah tren berdasarkan posisi harga dan Moving Averages."""
    if sma_20 is None:
        return "neutral"

    if sma_50 is not None:
        if current_price > sma_20 and sma_20 >= sma_50:
            return "strong_bullish"
        if current_price < sma_20 and sma_20 <= sma_50:
            return "strong_bearish"

    if current_price > sma_20:
        return "bullish"
    elif current_price < sma_20:
        return "bearish"

    return "neutral"
