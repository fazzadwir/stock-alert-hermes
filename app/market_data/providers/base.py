"""
MarketPulse — app/market_data/providers/base.py
Interface (Protocol) yang harus diimplementasikan oleh semua provider.
Ini memungkinkan provider diganti tanpa mengubah handlers atau service.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from app.domain.market_schemas import QuoteResult


@runtime_checkable
class MarketDataProvider(Protocol):
    """
    Kontrak interface untuk semua market data provider.
    Setiap provider harus mengimplementasikan kedua method ini.
    """

    async def get_quote(self, symbol: str) -> QuoteResult:
        """
        Ambil quote terkini untuk symbol yang diberikan.

        Args:
            symbol: Ticker symbol (misalnya 'AAPL', 'BBCA.JK', 'GC=F')

        Returns:
            QuoteResult — selalu dikembalikan, bisa berisi error state.
            Method ini tidak boleh raise exception yang tidak tertangani.
        """
        ...

    async def get_history(
        self,
        symbol: str,
        period: str,
        interval: str,
    ) -> object:
        """
        Ambil data historis untuk keperluan indikator teknikal (Phase 4).

        Args:
            symbol: Ticker symbol
            period: Periode data (misalnya '1mo', '3mo', '1y')
            interval: Interval data (misalnya '1d', '1h')

        Returns:
            Data historis dalam format yang sesuai dengan implementasi provider.
        """
        ...

    @property
    def provider_name(self) -> str:
        """Nama provider untuk ditampilkan di output dan log."""
        ...
