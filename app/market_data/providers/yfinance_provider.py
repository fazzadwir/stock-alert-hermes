"""
MarketPulse — app/market_data/providers/yfinance_provider.py

Adapter untuk yfinance sebagai market data provider.

KETERBATASAN YANG HARUS DIPAHAMI:
- yfinance bukan API resmi Yahoo Finance. Tidak ada SLA atau garansi availability.
- Data saham IDX (*.JK) umumnya delayed ~15-20 menit.
- yfinance tidak secara eksplisit menyatakan apakah data adalah real-time atau delayed.
- GC=F adalah Emas Futures COMEX, BUKAN harga spot atau harga Antam/Pegadaian.
- Operasi yfinance bersifat blocking; dijalankan di executor agar tidak memblokir event loop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from app.domain.market_schemas import DataStatus, InstrumentType, QuoteResult

logger = logging.getLogger(__name__)

# Mapping tipe instrument dari yfinance quoteType ke InstrumentType
_QUOTE_TYPE_MAP: dict[str, InstrumentType] = {
    "EQUITY": InstrumentType.EQUITY,
    "ETF": InstrumentType.ETF,
    "FUTURE": InstrumentType.FUTURES,
    "FUTURES": InstrumentType.FUTURES,
    "CRYPTOCURRENCY": InstrumentType.CRYPTO,
    "CURRENCY": InstrumentType.FOREX,
    "INDEX": InstrumentType.INDEX,
}

# Symbol yang diketahui sebagai futures
_KNOWN_FUTURES_SYMBOLS = frozenset({"GC=F", "SI=F", "CL=F", "NG=F", "ZC=F"})


class YFinanceProvider:
    """
    yfinance market data provider.

    Semua operasi yfinance dijalankan di thread pool executor
    karena yfinance bersifat blocking (sync HTTP requests).
    """

    def __init__(self, timeout_seconds: int = 15) -> None:
        self._timeout = timeout_seconds

    @property
    def provider_name(self) -> str:
        return "yfinance"

    async def get_quote(self, symbol: str) -> QuoteResult:
        """
        Ambil quote terkini untuk symbol.
        Selalu mengembalikan QuoteResult, tidak pernah raise exception ke caller.
        """
        fetch_ts = datetime.now(timezone.utc)
        symbol_upper = symbol.upper().strip()

        try:
            raw = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._fetch_quote_sync, symbol_upper
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("yfinance timeout untuk symbol: %s", symbol_upper)
            return QuoteResult(
                symbol=symbol_upper,
                fetch_timestamp=fetch_ts,
                source=self.provider_name,
                data_status=DataStatus.UNAVAILABLE,
                error="provider_timeout",
                error_message=f"Timeout setelah {self._timeout}s saat mengambil data dari provider.",
            )
        except Exception as exc:
            logger.error("yfinance error tidak terduga untuk %s: %s", symbol_upper, type(exc).__name__)
            return QuoteResult(
                symbol=symbol_upper,
                fetch_timestamp=fetch_ts,
                source=self.provider_name,
                data_status=DataStatus.UNAVAILABLE,
                error="provider_error",
                error_message="Terjadi kesalahan saat mengambil data dari provider.",
            )

        if raw is None:
            return QuoteResult(
                symbol=symbol_upper,
                fetch_timestamp=fetch_ts,
                source=self.provider_name,
                data_status=DataStatus.UNAVAILABLE,
                error="invalid_symbol",
                error_message=f"Simbol '{symbol_upper}' tidak ditemukan di provider.",
            )

        return self._parse_raw_quote(symbol_upper, raw, fetch_ts)

    def _fetch_quote_sync(self, symbol: str) -> Optional[dict[str, Any]]:
        """
        Operasi blocking: ambil data dari Yahoo Finance / yfinance.
        Pertama mencoba Yahoo Finance v8 chart API langsung dengan custom User-Agent
        (menghindari issue 429 crumb pada VPS/cloud server), lalu fallback ke yfinance Ticker.
        Returns None jika symbol tidak ditemukan atau data kosong.
        """
        # 1. Coba direct Yahoo Finance v8 chart endpoint
        try:
            import requests  # noqa: PLC0415

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
            resp = requests.get(url, headers=headers, timeout=self._timeout)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("chart", {}).get("result")
                if results and len(results) > 0:
                    meta = results[0].get("meta", {})
                    price = meta.get("regularMarketPrice")
                    if price is not None:
                        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
                        return {
                            "currentPrice": price,
                            "regularMarketPrice": price,
                            "previousClose": prev_close,
                            "regularMarketPreviousClose": prev_close,
                            "currency": meta.get("currency"),
                            "quoteType": meta.get("instrumentType"),
                            "longName": meta.get("longName") or meta.get("shortName") or symbol,
                            "shortName": meta.get("shortName") or symbol,
                            "exchange": meta.get("exchangeName"),
                            "regularMarketTime": meta.get("regularMarketTime"),
                        }
        except Exception as exc:
            logger.debug("Direct Yahoo chart endpoint gagal untuk %s: %s", symbol, exc)

        # 2. Fallback ke yfinance Ticker
        try:
            import yfinance as yf  # noqa: PLC0415 — import di sini untuk isolasi

            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info or not isinstance(info, dict):
                return None

            # Jika hanya ada satu key dan isinya tidak berguna, anggap symbol invalid
            # yfinance kadang return dict dengan satu key 'trailingPegRatio' untuk symbol tidak valid
            price_fields = {
                "currentPrice", "regularMarketPrice", "price",
                "ask", "bid", "navPrice", "previousClose",
                "regularMarketPreviousClose",
            }
            if not any(f in info for f in price_fields):
                logger.debug("yfinance: tidak ada field harga untuk %s. Keys: %s", symbol, list(info.keys())[:10])
                return None

            return info

        except Exception as exc:
            logger.error("_fetch_quote_sync error untuk %s: %s", symbol, type(exc).__name__)
            return None

    def _parse_raw_quote(
        self,
        symbol: str,
        info: dict[str, Any],
        fetch_ts: datetime,
    ) -> QuoteResult:
        """Parse dict info dari yfinance menjadi QuoteResult yang terstruktur."""

        # ── Harga ────────────────────────────────────────────────────────────
        price_raw = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("price")
            or info.get("ask")
            or info.get("navPrice")
        )

        prev_close_raw = (
            info.get("previousClose")
            or info.get("regularMarketPreviousClose")
        )

        if price_raw is None:
            return QuoteResult(
                symbol=symbol,
                fetch_timestamp=fetch_ts,
                source=self.provider_name,
                data_status=DataStatus.UNAVAILABLE,
                error="invalid_symbol",
                error_message=f"Data harga tidak tersedia untuk simbol '{symbol}'.",
            )

        price = Decimal(str(price_raw))
        prev_close: Optional[Decimal] = None
        price_change: Optional[Decimal] = None
        price_change_pct: Optional[Decimal] = None

        if prev_close_raw is not None:
            try:
                prev_close = Decimal(str(prev_close_raw))
                if prev_close > 0:
                    price_change = price - prev_close
                    price_change_pct = (price_change / prev_close * 100).quantize(Decimal("0.01"))
            except Exception:
                prev_close = None

        # ── Instrument type ──────────────────────────────────────────────────
        quote_type_raw: str = info.get("quoteType", "").upper()
        instrument_type = _QUOTE_TYPE_MAP.get(quote_type_raw, InstrumentType.UNKNOWN)

        # Override untuk simbol yang diketahui sebagai futures
        if symbol in _KNOWN_FUTURES_SYMBOLS:
            instrument_type = InstrumentType.FUTURES

        # ── Provider timestamp ───────────────────────────────────────────────
        provider_ts: Optional[datetime] = None
        reg_ts = info.get("regularMarketTime")
        if reg_ts:
            try:
                if isinstance(reg_ts, (int, float)):
                    provider_ts = datetime.fromtimestamp(reg_ts, tz=timezone.utc)
                elif isinstance(reg_ts, datetime):
                    provider_ts = reg_ts if reg_ts.tzinfo else reg_ts.replace(tzinfo=timezone.utc)
            except Exception:
                provider_ts = None

        # ── Data status ──────────────────────────────────────────────────────
        # yfinance tidak secara eksplisit menyatakan data adalah real-time.
        # Saham IDX umumnya delayed ~15-20 menit. Kita gunakan LAST_CLOSE atau UNKNOWN.
        market_state = info.get("marketState", "").upper()
        if market_state in ("REGULAR", "PRE", "POST"):
            # Market sedang buka, tapi kita tidak bisa konfirmasi real-time
            data_status = DataStatus.UNKNOWN
        else:
            # Market tutup atau state tidak diketahui
            data_status = DataStatus.LAST_CLOSE if prev_close is not None else DataStatus.UNKNOWN

        # ── Display name ─────────────────────────────────────────────────────
        display_name = (
            info.get("longName")
            or info.get("shortName")
            or info.get("name")
        )

        # ── Currency dan exchange ─────────────────────────────────────────────
        currency = info.get("currency", "").upper() or None
        exchange = info.get("exchange") or info.get("fullExchangeName")

        return QuoteResult(
            symbol=symbol,
            display_name=display_name,
            exchange=exchange,
            instrument_type=instrument_type,
            price=price,
            currency=currency,
            previous_close=prev_close,
            price_change=price_change,
            price_change_pct=price_change_pct,
            provider_timestamp=provider_ts,
            fetch_timestamp=fetch_ts,
            source=self.provider_name,
            data_status=data_status,
        )

    async def get_history(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> Any:
        """
        Ambil data historis. Digunakan oleh Phase 4 (Indicators).
        Saat ini mengembalikan raw yfinance DataFrame.
        """
        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._fetch_history_sync, symbol.upper(), period, interval
                ),
                timeout=self._timeout,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("yfinance history timeout untuk %s", symbol)
            return None
        except Exception as exc:
            logger.error("yfinance history error untuk %s: %s", symbol, type(exc).__name__)
            return None

    def _fetch_history_sync(self, symbol: str, period: str, interval: str) -> Any:
        """Blocking: ambil historis dari yfinance."""
        try:
            import yfinance as yf  # noqa: PLC0415
            ticker = yf.Ticker(symbol)
            return ticker.history(period=period, interval=interval)
        except Exception as exc:
            logger.error("_fetch_history_sync error untuk %s: %s", symbol, type(exc).__name__)
            return None
