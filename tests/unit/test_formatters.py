"""
Unit tests untuk app/bot/formatters.py
Memastikan formatting pesan benar, jujur tentang data, dan tidak bocor secrets.
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from datetime import datetime, timezone

from app.bot.formatters import (
    format_access_denied,
    format_error,
    format_help_message,
    format_quote,
    format_start_message,
)
from app.domain.market_schemas import DataStatus, InstrumentType, QuoteResult


class TestFormatStartMessage:
    def test_contains_welcome_text(self):
        msg = format_start_message()
        assert "MarketPulse" in msg

    def test_contains_disclaimer(self):
        msg = format_start_message()
        assert "rekomendasi investasi" in msg.lower() or "informasi" in msg.lower()

    def test_is_string(self):
        assert isinstance(format_start_message(), str)

    def test_not_empty(self):
        assert len(format_start_message()) > 0


class TestFormatHelpMessage:
    def test_contains_commands(self):
        msg = format_help_message()
        assert "/start" in msg
        assert "/help" in msg
        assert "/stock" in msg
        assert "/gold" in msg

    def test_contains_example_tickers(self):
        msg = format_help_message()
        assert "AAPL" in msg or "BBCA.JK" in msg

    def test_contains_limitations_info(self):
        """Help message harus menyebutkan keterbatasan data."""
        msg = format_help_message()
        assert "yfinance" in msg or "delayed" in msg.lower() or "keterbatasan" in msg.lower()

    def test_gold_disclaimer_in_help(self):
        """Help harus menyebutkan bahwa GC=F adalah futures."""
        msg = format_help_message()
        assert "GC=F" in msg
        # Pastikan ada label futures/COMEX/spot
        assert any(word in msg for word in ["futures", "COMEX", "spot"])


class TestFormatQuote:
    def test_equity_quote_contains_symbol(self, sample_aapl_quote):
        msg = format_quote(sample_aapl_quote)
        assert "AAPL" in msg

    def test_equity_quote_contains_price(self, sample_aapl_quote):
        msg = format_quote(sample_aapl_quote)
        assert "182" in msg  # Harga $182.50

    def test_equity_quote_contains_currency(self, sample_aapl_quote):
        msg = format_quote(sample_aapl_quote)
        assert "USD" in msg or "$" in msg

    def test_idr_formatted_without_decimal(self, sample_bbca_quote):
        """Harga IDR tidak boleh punya desimal."""
        msg = format_quote(sample_bbca_quote)
        assert "9.875" in msg or "9,875" in msg  # format ribuan

    def test_idr_uses_rp_prefix(self, sample_bbca_quote):
        msg = format_quote(sample_bbca_quote)
        assert "Rp" in msg

    def test_change_shown_when_valid(self, sample_aapl_quote):
        """Perubahan harga harus ditampilkan jika data valid."""
        msg = format_quote(sample_aapl_quote)
        assert "1.39" in msg or "2.50" in msg or "▲" in msg

    def test_no_change_shown_without_prev_close(self):
        """Perubahan TIDAK boleh ditampilkan jika tidak ada previous_close."""
        quote = QuoteResult(
            symbol="TEST",
            price=Decimal("100"),
            currency="USD",
            source="yfinance",
            data_status=DataStatus.UNKNOWN,
            # previous_close sengaja tidak diset
        )
        msg = format_quote(quote)
        # Tidak boleh ada angka persentase yang dikarang
        assert "%" not in msg or "tidak tersedia" in msg.lower()

    def test_gold_futures_disclaimer(self, sample_gold_quote):
        """Quote GC=F harus menampilkan disclaimer futures."""
        msg = format_quote(sample_gold_quote)
        # Harus ada salah satu kata kunci yang menjelaskan ini adalah futures
        assert any(word in msg for word in ["futures", "COMEX", "spot", "GC=F"])

    def test_instrument_type_shown(self, sample_aapl_quote):
        """Jenis instrumen harus ditampilkan."""
        msg = format_quote(sample_aapl_quote)
        assert "Saham" in msg or "equity" in msg.lower()

    def test_provider_name_shown(self, sample_aapl_quote):
        """Nama provider harus ditampilkan."""
        msg = format_quote(sample_aapl_quote)
        assert "yfinance" in msg

    def test_status_label_shown(self, sample_aapl_quote):
        """Status data harus ditampilkan."""
        msg = format_quote(sample_aapl_quote)
        # Salah satu label status harus ada
        assert any(word in msg for word in ["Real-time", "Delayed", "Penutupan", "Status", "diketahui"])

    def test_does_not_claim_realtime_without_basis(self, sample_aapl_quote):
        """
        Tidak boleh mengklaim data real-time jika DataStatus bukan REALTIME.
        sample_aapl_quote menggunakan DataStatus.UNKNOWN.
        """
        assert sample_aapl_quote.data_status != DataStatus.REALTIME
        msg = format_quote(sample_aapl_quote)
        # "Real-time" tidak boleh muncul untuk status UNKNOWN
        assert "🟢 Real-time" not in msg

    def test_disclaimer_present(self, sample_aapl_quote):
        """Disclaimer investasi harus selalu ada."""
        msg = format_quote(sample_aapl_quote)
        assert "rekomendasi" in msg.lower() or "⚠️" in msg

    def test_failed_quote_shows_error(self, invalid_symbol_quote):
        """Quote yang gagal harus menampilkan error message, bukan harga."""
        msg = format_quote(invalid_symbol_quote)
        assert "INVALID123XYZ" in msg
        assert "tidak ditemukan" in msg.lower() or "❌" in msg

    def test_html_escaping_in_symbol(self):
        """Symbol dengan karakter HTML harus di-escape."""
        quote = QuoteResult(
            symbol="A&B",
            price=Decimal("100"),
            currency="USD",
            source="yfinance",
            data_status=DataStatus.UNKNOWN,
        )
        msg = format_quote(quote)
        # Harus ada escaped version
        assert "&amp;" in msg or "A&B" not in msg.replace("&amp;", "")


class TestFormatError:
    def test_invalid_symbol_error(self, invalid_symbol_quote):
        msg = format_error(invalid_symbol_quote)
        assert "❌" in msg or "tidak ditemukan" in msg.lower()

    def test_timeout_error(self, timeout_quote):
        msg = format_error(timeout_quote)
        assert "⏱" in msg or "timeout" in msg.lower() or "Timeout" in msg

    def test_error_never_contains_traceback(self, invalid_symbol_quote):
        """Pesan error tidak boleh mengandung stack trace."""
        msg = format_error(invalid_symbol_quote)
        assert "Traceback" not in msg
        assert "File " not in msg
        assert "line " not in msg

    def test_error_contains_symbol(self, invalid_symbol_quote):
        msg = format_error(invalid_symbol_quote)
        assert "INVALID123XYZ" in msg


class TestFormatAccessDenied:
    def test_access_denied_message(self):
        msg = format_access_denied()
        assert "🔒" in msg or "ditolak" in msg.lower()
        assert isinstance(msg, str)
        assert len(msg) > 0
