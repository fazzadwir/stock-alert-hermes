"""
MarketPulse — app/market_data/service.py
MarketDataService — layer antara bot handlers dan provider.
Bertanggung jawab untuk caching, validasi symbol, dan error normalization.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Optional, Tuple

from app.domain.market_schemas import DataStatus, QuoteResult
from app.market_data.providers.base import MarketDataProvider

logger = logging.getLogger(__name__)

# Cache entry: (QuoteResult, timestamp_float)
_CacheEntry = Tuple[QuoteResult, float]


class MarketDataService:
    """
    Service layer untuk market data.
    Menyediakan caching in-memory sederhana untuk mengurangi request ke provider.
    """

    def __init__(
        self,
        provider: MarketDataProvider,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self._provider = provider
        self._cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, _CacheEntry] = {}
        self._cache_lock = asyncio.Lock()

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    async def get_quote(self, symbol: str) -> QuoteResult:
        """
        Ambil quote dengan caching.
        Cache disimpan per symbol (uppercase).
        Cache dianggap valid selama cache_ttl_seconds.
        Cache tidak digunakan jika hasil sebelumnya adalah error.
        """
        symbol_norm = symbol.upper().strip()

        # Cek cache
        async with self._cache_lock:
            entry = self._cache.get(symbol_norm)
            if entry is not None:
                cached_result, cached_at = entry
                age = time.monotonic() - cached_at
                if age < self._cache_ttl and not cached_result.is_failed:
                    logger.debug("Cache hit untuk %s (umur %.1fs)", symbol_norm, age)
                    return cached_result

        # Ambil dari provider
        logger.info("Mengambil quote untuk %s dari provider %s", symbol_norm, self._provider.provider_name)
        result = await self._provider.get_quote(symbol_norm)

        # Simpan ke cache jika berhasil
        if not result.is_failed:
            async with self._cache_lock:
                self._cache[symbol_norm] = (result, time.monotonic())

        return result

    async def get_gold_quote(self) -> QuoteResult:
        """
        Ambil harga emas menggunakan simbol GC=F (Gold Futures COMEX).

        CATATAN PENTING: GC=F adalah kontrak futures emas di COMEX,
        BUKAN harga spot emas atau harga ritel (Antam/Pegadaian).
        Harga dalam USD per troy ounce.
        """
        return await self.get_quote("GC=F")

    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """
        Bersihkan cache.
        Jika symbol diberikan, hanya hapus cache untuk symbol tersebut.
        Jika tidak, bersihkan semua cache.
        """
        if symbol:
            self._cache.pop(symbol.upper().strip(), None)
        else:
            self._cache.clear()
