"""
MarketPulse — app/bot/formatters.py
Formatter untuk pesan Telegram.
Memisahkan logika formatting dari pengambilan data dan command handling.
Semua output dalam Bahasa Indonesia.
Gunakan HTML parse mode agar lebih aman dari karakter khusus MarkdownV2.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from app.domain.market_schemas import DataStatus, InstrumentType, QuoteResult

# ─── Konstanta tampilan ────────────────────────────────────────────────────────

_STATUS_LABEL: dict[DataStatus, str] = {
    DataStatus.REALTIME: "🟢 Real-time",
    DataStatus.DELAYED: "🟡 Delayed",
    DataStatus.LAST_CLOSE: "🔵 Penutupan terakhir",
    DataStatus.STALE: "🟠 Data lama",
    DataStatus.UNAVAILABLE: "🔴 Tidak tersedia",
    DataStatus.UNKNOWN: "⚪ Status tidak diketahui",
}

_INSTRUMENT_LABEL: dict[InstrumentType, str] = {
    InstrumentType.EQUITY: "Saham",
    InstrumentType.ETF: "ETF",
    InstrumentType.FUTURES: "Futures",
    InstrumentType.CRYPTO: "Kripto",
    InstrumentType.FOREX: "Forex",
    InstrumentType.INDEX: "Indeks",
    InstrumentType.UNKNOWN: "Instrumen",
}

_WIB_OFFSET = 7 * 3600  # UTC+7 dalam detik


def _to_wib(dt: Optional[datetime]) -> Optional[str]:
    """Konversi datetime ke string WIB (UTC+7). Return None jika dt adalah None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Konversi ke UTC+7
    from datetime import timedelta, timezone as tz
    wib = tz(timedelta(hours=7), name="WIB")
    dt_wib = dt.astimezone(wib)
    return dt_wib.strftime("%d %b %Y %H:%M:%S WIB")


def _format_price(price: Optional[Decimal], currency: Optional[str]) -> str:
    """Format harga dengan mata uang. Return '–' jika tidak ada."""
    if price is None:
        return "–"
    currency_str = currency.upper() if currency else ""

    # Format IDR tanpa desimal, USD dengan 2 desimal
    if currency_str == "IDR":
        formatted = f"Rp {price:,.0f}"
    elif currency_str == "USD":
        formatted = f"${price:,.2f}"
    else:
        formatted = f"{price:,.4f}" if price < 1 else f"{price:,.2f}"
        if currency_str:
            formatted = f"{currency_str} {formatted}"

    return formatted


def _format_change(
    price_change: Optional[Decimal],
    price_change_pct: Optional[Decimal],
    currency: Optional[str],
) -> Optional[str]:
    """
    Format perubahan harga. Return None jika data tidak cukup.
    TIDAK MENAMPILKAN perubahan jika baseline tidak valid.
    """
    if price_change is None or price_change_pct is None:
        return None

    currency_str = currency.upper() if currency else ""
    arrow = "▲" if price_change >= 0 else "▼"
    sign = "+" if price_change >= 0 else ""

    if currency_str == "IDR":
        change_str = f"{sign}Rp {price_change:,.0f}"
    elif currency_str == "USD":
        change_str = f"{sign}${price_change:,.2f}"
    else:
        change_str = f"{sign}{price_change:,.2f}"
        if currency_str:
            change_str = f"{currency_str} {change_str}"

    pct_str = f"{sign}{price_change_pct:.2f}%"
    return f"{arrow} {change_str} ({pct_str})"


def format_quote(quote: QuoteResult) -> str:
    """
    Format QuoteResult menjadi pesan Telegram siap kirim.
    Gunakan HTML parse mode.
    Jujur tentang keterbatasan data.
    """
    if quote.is_failed:
        return format_error(quote)

    lines: list[str] = []

    # Header
    instrument_label = _INSTRUMENT_LABEL.get(quote.instrument_type, "Instrumen")
    name_part = f" — {html.escape(quote.display_name)}" if quote.display_name else ""
    exchange_part = f" ({html.escape(quote.exchange)})" if quote.exchange else ""
    lines.append(f"📊 <b>{html.escape(quote.symbol)}</b>{name_part}{exchange_part}")
    lines.append(f"<i>Jenis: {instrument_label}</i>")
    lines.append("")

    # Peringatan khusus untuk futures emas
    if quote.symbol == "GC=F" or quote.instrument_type == InstrumentType.FUTURES:
        if quote.symbol == "GC=F":
            lines.append(
                "⚠️ <i>GC=F adalah kontrak emas futures COMEX (bukan harga spot/Antam/Pegadaian).</i>"
            )
            lines.append("")

    # Harga
    price_str = _format_price(quote.price, quote.currency)
    lines.append(f"💰 <b>Harga:</b> {price_str}")

    # Perubahan — hanya tampilkan jika data valid
    if quote.has_change:
        change_str = _format_change(quote.price_change, quote.price_change_pct, quote.currency)
        if change_str:
            prev_str = _format_price(quote.previous_close, quote.currency)
            lines.append(f"📈 <b>Perubahan:</b> {change_str}")
            lines.append(f"   <i>vs penutupan sebelumnya: {prev_str}</i>")
    elif quote.price is not None:
        lines.append("📈 <b>Perubahan:</b> –  <i>(data penutupan sebelumnya tidak tersedia)</i>")

    lines.append("")

    # Metadata data
    status_label = _STATUS_LABEL.get(quote.data_status, "⚪ Tidak diketahui")
    lines.append(f"🔄 <b>Status data:</b> {status_label}")

    # Timestamp provider
    if quote.provider_timestamp:
        ts_str = _to_wib(quote.provider_timestamp)
        lines.append(f"🕐 <b>Waktu data:</b> {ts_str}")
    else:
        lines.append("🕐 <b>Waktu data:</b> –  <i>(tidak tersedia dari provider)</i>")

    # Waktu pengambilan
    if quote.fetch_timestamp:
        fetch_str = _to_wib(quote.fetch_timestamp)
        lines.append(f"🔃 <b>Diambil:</b> {fetch_str}")

    lines.append(f"📡 <b>Provider:</b> {html.escape(quote.source)}")

    # Disclaimer
    lines.append("")
    lines.append(
        "<i>⚠️ Data bukan rekomendasi investasi. "
        "Verifikasi ke sumber resmi sebelum mengambil keputusan.</i>"
    )

    return "\n".join(lines)


def format_error(quote: QuoteResult) -> str:
    """Format pesan error ketika quote gagal diambil."""
    error_messages: dict[str, str] = {
        "invalid_symbol": f"❌ Simbol <b>{html.escape(quote.symbol)}</b> tidak ditemukan.\n"
                          "Periksa kembali simbol yang Anda masukkan.\n"
                          "Contoh: <code>AAPL</code>, <code>BBCA.JK</code>, <code>GOOGL</code>",
        "provider_timeout": f"⏱ Timeout saat mengambil data untuk <b>{html.escape(quote.symbol)}</b>.\n"
                            "Provider tidak merespons dalam waktu yang ditentukan. Coba lagi nanti.",
        "provider_error": f"⚠️ Terjadi kesalahan saat mengambil data untuk <b>{html.escape(quote.symbol)}</b>.\n"
                          "Provider sedang tidak tersedia. Coba lagi beberapa saat.",
        "rate_limited": f"🚫 Terlalu banyak permintaan untuk <b>{html.escape(quote.symbol)}</b>.\n"
                        "Tunggu beberapa saat sebelum mencoba lagi.",
    }

    error_code = quote.error or "provider_error"
    message = error_messages.get(error_code)

    if message is None:
        message = (
            f"❌ Gagal mengambil data untuk <b>{html.escape(quote.symbol)}</b>.\n"
            "Coba lagi atau periksa koneksi."
        )

    return message


def format_start_message() -> str:
    """Format pesan /start."""
    return (
        "👋 <b>Selamat datang di MarketPulse!</b>\n\n"
        "Bot ini membantu Anda memantau saham Indonesia, saham internasional, "
        "dan emas langsung dari Telegram.\n\n"
        "Gunakan /help untuk melihat daftar perintah yang tersedia.\n\n"
        "<i>⚠️ MarketPulse adalah alat informasi, bukan rekomendasi investasi.</i>"
    )


def format_help_message() -> str:
    """Format pesan /help."""
    return (
        "📖 <b>Panduan MarketPulse</b>\n\n"
        "<b>Perintah yang tersedia:</b>\n\n"
        "• /start — Perkenalan bot\n"
        "• /help — Tampilkan panduan ini\n"
        "• /stock &lt;ticker&gt; — Cek harga saham\n"
        "• /gold — Cek harga emas futures COMEX\n\n"
        "<b>Contoh penggunaan:</b>\n"
        "<code>/stock AAPL</code> — Apple Inc.\n"
        "<code>/stock BBCA.JK</code> — Bank BCA (IDX)\n"
        "<code>/stock TLKM.JK</code> — Telkom Indonesia\n"
        "<code>/stock GOOGL</code> — Alphabet (Google)\n"
        "<code>/gold</code> — Emas futures COMEX (GC=F)\n\n"
        "<b>Format ticker saham Indonesia (IDX):</b>\n"
        "Tambahkan <code>.JK</code> di akhir kode saham.\n"
        "Contoh: <code>BBCA.JK</code>, <code>BMRI.JK</code>, <code>ASII.JK</code>\n\n"
        "<b>Keterbatasan data:</b>\n"
        "• Data IDX umumnya delayed 15-20 menit\n"
        "• <code>GC=F</code> adalah emas futures COMEX, bukan harga spot/Antam\n"
        "• Provider: yfinance (bukan API resmi Yahoo Finance)\n\n"
        "<i>Fitur watchlist, alert, dan analisis AI sedang dalam pengembangan.</i>"
    )


def format_access_denied() -> str:
    """Format pesan akses ditolak."""
    return "🔒 Akses ditolak. Bot ini hanya untuk pengguna yang diizinkan."


def format_token_not_configured() -> str:
    """Format pesan token belum dikonfigurasi."""
    return "⚙️ Bot belum dikonfigurasi. Hubungi administrator."
