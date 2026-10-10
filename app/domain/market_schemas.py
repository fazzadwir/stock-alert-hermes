"""
MarketPulse — app/domain/market_schemas.py
Domain schemas untuk data pasar. Digunakan oleh provider, service, dan formatter.
Semua operasi harga menggunakan Decimal untuk presisi.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator


class DataStatus(str, Enum):
    """Status freshness data pasar."""
    REALTIME = "realtime"       # Provider menjamin real-time (jarang untuk free tier)
    DELAYED = "delayed"         # Data delayed (misalnya 15-20 menit untuk IDX)
    LAST_CLOSE = "last_close"   # Data penutupan terakhir (market tutup)
    STALE = "stale"             # Data tersedia tapi lebih lama dari expected
    UNAVAILABLE = "unavailable" # Data tidak bisa diambil sama sekali
    UNKNOWN = "unknown"         # Status tidak bisa ditentukan dari metadata provider


class InstrumentType(str, Enum):
    """Jenis instrumen keuangan."""
    EQUITY = "equity"               # Saham
    ETF = "etf"                     # ETF
    FUTURES = "futures"             # Futures (termasuk GC=F untuk emas)
    CRYPTO = "crypto"               # Kripto
    FOREX = "forex"                 # Mata uang
    INDEX = "index"                 # Indeks
    UNKNOWN = "unknown"             # Tidak bisa ditentukan


class QuoteResult(BaseModel):
    """
    Hasil quote satu instrumen dari provider.
    Semua field opsional kecuali symbol dan status.
    Provider harus mengisi field yang tersedia dan menjelaskan keterbatasannya.
    """

    # Identifikasi
    symbol: str
    display_name: Optional[str] = None          # Nama instrumen (jika tersedia)
    exchange: Optional[str] = None              # Nama bursa
    instrument_type: InstrumentType = InstrumentType.UNKNOWN

    # Harga — gunakan Decimal untuk presisi finansial
    price: Optional[Decimal] = None
    currency: Optional[str] = None
    previous_close: Optional[Decimal] = None    # Penutupan sebelumnya (basis perubahan)
    price_change: Optional[Decimal] = None      # Selisih harga vs previous_close
    price_change_pct: Optional[Decimal] = None  # Persentase perubahan

    # Metadata waktu
    provider_timestamp: Optional[datetime] = None   # Timestamp dari provider/sumber data
    fetch_timestamp: Optional[datetime] = None      # Waktu pengambilan data oleh bot

    # Metadata provider
    source: str = "unknown"                         # Nama provider
    data_status: DataStatus = DataStatus.UNKNOWN

    # Error state
    error: Optional[str] = None                     # Error code jika gagal
    error_message: Optional[str] = None             # Pesan error yang aman untuk log

    @field_validator("price", "previous_close", "price_change", "price_change_pct", mode="before")
    @classmethod
    def coerce_to_decimal(cls, v: object) -> Optional[Decimal]:
        """Konversi float/int/str ke Decimal. None tetap None."""
        if v is None:
            return None
        try:
            return Decimal(str(v))
        except Exception:
            return None

    @property
    def has_price(self) -> bool:
        """True jika harga tersedia."""
        return self.price is not None

    @property
    def has_change(self) -> bool:
        """True jika perubahan harga dapat dihitung secara valid."""
        return (
            self.price is not None
            and self.previous_close is not None
            and self.previous_close > 0
            and self.price_change is not None
            and self.price_change_pct is not None
        )

    @property
    def is_failed(self) -> bool:
        """True jika quote gagal diambil."""
        return self.error is not None or self.data_status == DataStatus.UNAVAILABLE

    class Config:
        use_enum_values = False
