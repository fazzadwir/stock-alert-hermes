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
        "• /gold — Cek harga emas futures COMEX\n"
        "• /watchlist — Lihat seluruh aset di watchlist Anda\n"
        "• /market — Snapshot pergerakan harga watchlist\n"
        "• /add &lt;ticker&gt; [catatan] — Tambah aset ke watchlist\n"
        "• /remove &lt;ticker&gt; — Hapus aset dari watchlist\n"
        "• /alert &lt;ticker&gt; &lt;above|below&gt; &lt;target&gt; — Buat alert target harga\n"
        "• /alerts — Daftar alert aktif Anda\n"
        "• /delalert &lt;id&gt; — Hapus alert berdasarkan ID\n\n"
        "<b>Contoh penggunaan:</b>\n"
        "<code>/stock AAPL</code> — Cek Apple Inc.\n"
        "<code>/stock BBCA.JK</code> — Cek Bank BCA (IDX)\n"
        "<code>/gold</code> — Cek emas futures COMEX (GC=F)\n"
        "<code>/add BBCA.JK Core banking</code> — Tambah ke watchlist\n"
        "<code>/alert BBCA.JK above 6200</code> — Alert jika BCA naik ke Rp 6.200\n"
        "<code>/alert AAPL below 210</code> — Alert jika Apple turun ke $210\n"
        "<code>/alerts</code> — Lihat semua alert aktif\n"
        "<code>/delalert 1</code> — Hapus alert #1\n\n"
        "<b>Format ticker saham Indonesia (IDX):</b>\n"
        "Tambahkan <code>.JK</code> di akhir kode saham.\n"
        "Contoh: <code>BBCA.JK</code>, <code>BMRI.JK</code>, <code>ASII.JK</code>\n\n"
        "<b>Keterbatasan data:</b>\n"
        "• Data IDX umumnya delayed 15-20 menit\n"
        "• <code>GC=F</code> adalah emas futures COMEX, bukan harga spot/Antam\n"
        "• Provider: yfinance (bukan API resmi Yahoo Finance)\n\n"
        "<i>Fitur analisis AI sedang dalam pengembangan.</i>"
    )


def format_access_denied() -> str:
    """Format pesan akses ditolak."""
    return "🔒 Akses ditolak. Bot ini hanya untuk pengguna yang diizinkan."


def format_token_not_configured() -> str:
    """Format pesan token belum dikonfigurasi."""
    return "⚙️ Bot belum dikonfigurasi. Hubungi administrator."


# ─── Watchlist & Market Formatters ───────────────────────────────────────────


def format_watchlist_empty() -> str:
    """Format pesan ketika watchlist masih kosong."""
    return (
        "📋 <b>Watchlist Anda Masih Kosong</b>\n\n"
        "Belum ada aset yang dipantau. Gunakan perintah <code>/add</code> untuk menambahkan aset.\n\n"
        "<b>Contoh:</b>\n"
        "• <code>/add BBCA.JK Saham Banking</code>\n"
        "• <code>/add AAPL Apple Inc</code>\n"
        "• <code>/add GC=F Emas COMEX</code>"
    )


def format_watchlist(items_with_quotes: list[tuple[Any, QuoteResult]]) -> str:
    """
    Format daftar watchlist lengkap dengan harga saat ini dan perubahan.
    items_with_quotes: list of (WatchlistItem, QuoteResult)
    """
    if not items_with_quotes:
        return format_watchlist_empty()

    lines = [f"📋 <b>Watchlist Anda ({len(items_with_quotes)} aset)</b>\n"]

    for item, quote in items_with_quotes:
        symbol = html.escape(item.symbol)
        note_str = f" <i>({html.escape(item.note)})</i>" if getattr(item, "note", None) else ""

        if quote.is_failed or not quote.has_price:
            lines.append(f"• <b>{symbol}</b>{note_str}: <i>(Gagal memuat harga)</i>")
            continue

        price_str = _format_price(quote.price, quote.currency)

        # Perubahan harga
        if quote.has_change:
            arrow = "🟢 +" if quote.price_change > 0 else ("🔴 " if quote.price_change < 0 else "⚪ ")
            change_str = f" {arrow}{quote.price_change_pct:+.2f}%"
        else:
            change_str = ""

        lines.append(f"• <b>{symbol}</b>{note_str}: <code>{price_str}</code>{change_str}")

    lines.append("\n<i>Gunakan /market untuk snapshot lengkap atau /stock &lt;ticker&gt; untuk detail.</i>")
    return "\n".join(lines)


def format_market_summary(quotes: list[QuoteResult]) -> str:
    """Format ringkasan pasar untuk aset-aset dalam watchlist."""
    if not quotes:
        return format_watchlist_empty()

    lines = [
        "📊 <b>Snapshot Pasar Watchlist</b>\n",
    ]

    gainers = 0
    losers = 0
    unchanged = 0

    for q in quotes:
        symbol = html.escape(q.symbol)
        if q.is_failed or not q.has_price:
            lines.append(f"• <b>{symbol}</b>: <i>Data tidak tersedia</i>")
            continue

        price_str = _format_price(q.price, q.currency)

        if q.has_change:
            if q.price_change > 0:
                gainers += 1
                icon = "🟢"
            elif q.price_change < 0:
                losers += 1
                icon = "🔴"
            else:
                unchanged += 1
                icon = "⚪"
            change_str = f"{icon} {q.price_change_pct:+.2f}%"
        else:
            unchanged += 1
            change_str = "⚪ –"

        lines.append(f"• <b>{symbol}</b>: <code>{price_str}</code> ({change_str})")

    lines.append(f"\n<b>Ringkasan:</b> 🟢 {gainers} Naik | 🔴 {losers} Turun | ⚪ {unchanged} Flat")
    lines.append("<i>⚠️ Data IDX delayed 15-20 min. Emas adalah COMEX futures (GC=F).</i>")
    return "\n".join(lines)


def format_add_success(symbol: str, quote: QuoteResult, note: Optional[str] = None) -> str:
    """Format pesan sukses menambah item ke watchlist."""
    sym_escaped = html.escape(symbol.upper())
    note_escaped = f"\nCatatan: <i>{html.escape(note)}</i>" if note else ""
    price_info = ""
    if quote.has_price:
        price_info = f"\nHarga saat ini: <code>{_format_price(quote.price, quote.currency)}</code>"

    return (
        f"✅ <b>{sym_escaped}</b> berhasil ditambahkan ke watchlist!{note_escaped}{price_info}\n\n"
        f"Ketik <code>/watchlist</code> untuk melihat daftar pantauan."
    )


def format_add_exists(symbol: str) -> str:
    """Format pesan ketika item sudah ada di watchlist."""
    return f"ℹ️ Simbol <b>{html.escape(symbol.upper())}</b> sudah ada di watchlist Anda."


def format_add_limit_reached(max_limit: int) -> str:
    """Format pesan ketika watchlist sudah mencapai batas limit."""
    return (
        f"⚠️ Watchlist Anda telah mencapai batas maksimal ({max_limit} aset).\n"
        f"Hapus aset yang tidak dibutuhkan dengan <code>/remove &lt;ticker&gt;</code>."
    )


def format_remove_success(symbol: str) -> str:
    """Format pesan sukses menghapus item dari watchlist."""
    return f"🗑️ <b>{html.escape(symbol.upper())}</b> berhasil dihapus dari watchlist Anda."


def format_remove_not_found(symbol: str) -> str:
    """Format pesan ketika simbol tidak ditemukan di watchlist saat remove."""
    return f"❓ Simbol <b>{html.escape(symbol.upper())}</b> tidak ditemukan dalam watchlist Anda."


# ─── Alert Formatters ────────────────────────────────────────────────────────


def format_alert_created(
    alert_id: int,
    symbol: str,
    condition: str,
    target_value: Decimal,
    quote: Optional[QuoteResult] = None,
) -> str:
    """Format konfirmasi pembuatan alert baru."""
    cond_label = "naik di atas (≥)" if condition == "above" else "turun di bawah (≤)"
    price_info = ""
    if quote and quote.has_price:
        price_info = f"\nHarga saat ini: <code>{_format_price(quote.price, quote.currency)}</code>"

    return (
        f"🔔 <b>Alert #{alert_id} Berhasil Dibuat!</b>\n\n"
        f"• Simbol: <b>{html.escape(symbol.upper())}</b>\n"
        f"• Kondisi: <b>{cond_label}</b>\n"
        f"• Target: <code>{target_value:,.2f}</code>{price_info}\n\n"
        f"MarketPulse akan mengirim notifikasi saat harga menyentuh target.\n"
        f"Ketik <code>/alerts</code> untuk melihat semua alert aktif."
    )


def format_alerts_empty() -> str:
    """Format pesan saat user belum memiliki alert aktif."""
    return (
        "🔔 <b>Belum Ada Alert Aktif</b>\n\n"
        "Anda belum memiliki alert harga yang aktif.\n\n"
        "<b>Cara membuat alert:</b>\n"
        "• <code>/alert BBCA.JK above 6200</code> — Alert saat BCA ≥ 6200\n"
        "• <code>/alert AAPL below 220</code> — Alert saat Apple ≤ 220\n"
        "• <code>/alert GC=F above 2750</code> — Alert saat emas COMEX ≥ 2750"
    )


def format_alerts_list(alerts: list[Any]) -> str:
    """Format daftar alert aktif milik user."""
    if not alerts:
        return format_alerts_empty()

    lines = [f"🔔 <b>Daftar Alert Aktif ({len(alerts)})</b>\n"]

    for a in alerts:
        cond_icon = "📈 ≥" if a.condition == "above" else "📉 ≤"
        target_str = f"{a.target_value:,.2f}"
        note_str = f" <i>({html.escape(a.note)})</i>" if getattr(a, "note", None) else ""

        lines.append(
            f"• <b>#{a.id}</b> <code>{html.escape(a.symbol)}</code> {cond_icon} <b>{target_str}</b>{note_str}"
        )

    lines.append("\n<i>Gunakan /delalert &lt;id&gt; untuk membatalkan alert.</i>")
    return "\n".join(lines)


def format_alert_triggered(alert: Any, quote: QuoteResult) -> str:
    """
    Format notifikasi saat alert terpicu.
    Dikirimkan langsung ke chat Telegram pengguna.
    """
    symbol = html.escape(alert.symbol)
    cond_text = "naik menembus" if alert.condition == "above" else "turun menembus"
    price_str = _format_price(quote.price, quote.currency)
    note_line = f"\nCatatan: <i>{html.escape(alert.note)}</i>" if getattr(alert, "note", None) else ""

    change_line = ""
    if quote.has_change:
        arrow = "+" if quote.price_change > 0 else ""
        change_line = f"\nPerubahan hari ini: <code>{arrow}{quote.price_change_pct:+.2f}%</code>"

    wib_time = _to_wib(quote.fetch_timestamp) or "-"

    return (
        f"🚨 <b>MARKET ALERT TERPICU!</b>\n\n"
        f"📌 <b>{symbol}</b> telah {cond_text} target!\n"
        f"• Target Anda: <code>{alert.target_value:,.2f}</code>\n"
        f"• Harga Terkini: <b>{price_str}</b>{change_line}{note_line}\n"
        f"• Waktu: <i>{wib_time}</i>\n\n"
        f"<i>Status data: {_STATUS_LABEL.get(quote.data_status, quote.data_status.value)}</i>"
    )


def format_alert_deleted(alert_id: int) -> str:
    """Format pesan sukses menghapus alert."""
    return f"🗑️ Alert <b>#{alert_id}</b> berhasil dihapus."


def format_alert_not_found(alert_id: int) -> str:
    """Format pesan saat alert tidak ditemukan saat dihapus."""
    return f"❓ Alert <b>#{alert_id}</b> tidak ditemukan atau bukan milik Anda."


def format_alert_limit_reached(max_limit: int) -> str:
    """Format pesan saat kuota alert aktif penuh."""
    return (
        f"⚠️ Anda telah mencapai batas maksimal ({max_limit} alert aktif).\n"
        f"Hapus alert yang tidak dibutuhkan dengan <code>/delalert &lt;id&gt;</code>."
    )


# ─── Technical Analysis Formatter ───────────────────────────────────────────


def format_technical_analysis(ta: Any) -> str:
    """Format hasil analisis teknikal (RSI, Moving Averages, Tren, S/R)."""
    if getattr(ta, "is_failed", False):
        err = html.escape(getattr(ta, "error_message", None) or "Gagal memproses analisis teknikal.")
        return f"⚠️ <b>Analisis Teknikal Gagal ({html.escape(ta.symbol)})</b>\n\n{err}"

    symbol = html.escape(ta.symbol)
    price_str = _format_price(ta.current_price, ta.currency)

    # Format RSI
    if ta.rsi_14 is not None:
        if ta.rsi_status == "overbought":
            rsi_badge = "🔴 Overbought (≥70)"
        elif ta.rsi_status == "oversold":
            rsi_badge = "🟢 Oversold (≤30)"
        else:
            rsi_badge = "⚪ Netral (30-70)"
        rsi_line = f"• RSI (14): <code>{ta.rsi_14:.2f}</code> ({rsi_badge})"
    else:
        rsi_line = "• RSI (14): <i>Data tidak mencukupi</i>"

    # Format Moving Averages
    ma_lines = []
    if ta.sma_20 is not None:
        pos_20 = "Harga di atas MA20" if ta.price_vs_sma20 == "above" else "Harga di bawah MA20"
        ma_lines.append(f"• MA20: <code>{_format_price(ta.sma_20, ta.currency)}</code> ({pos_20})")
    if ta.sma_50 is not None:
        ma_lines.append(f"• MA50: <code>{_format_price(ta.sma_50, ta.currency)}</code>")

    # Format Tren & Persilangan
    trend_labels = {
        "strong_bullish": "🟢🟢 Sangat Bullish (Harga > MA20 ≥ MA50)",
        "bullish": "🟢 Bullish (Harga > MA20)",
        "strong_bearish": "🔴🔴 Sangat Bearish (Harga < MA20 ≤ MA50)",
        "bearish": "🔴 Bearish (Harga < MA20)",
        "neutral": "⚪ Netral / Konsolidasi",
    }
    trend_str = trend_labels.get(ta.ma_trend or "neutral", "⚪ Netral")

    crossover_line = ""
    if ta.ma_crossover == "golden_cross":
        crossover_line = "\n• Sinyal MA: ✨ <b>Golden Cross Terdeteksi!</b> (MA20 memotong ke atas MA50)"
    elif ta.ma_crossover == "death_cross":
        crossover_line = "\n• Sinyal MA: ⚠️ <b>Death Cross Terdeteksi!</b> (MA20 memotong ke bawah MA50)"

    # Format Support & Resistance
    sr_lines = []
    if ta.resistance_20d is not None:
        sr_lines.append(f"• Resistance (20H): <code>{_format_price(ta.resistance_20d, ta.currency)}</code>")
    if ta.support_20d is not None:
        sr_lines.append(f"• Support (20H): <code>{_format_price(ta.support_20d, ta.currency)}</code>")

    sr_section = ("\n\n🎯 <b>Level Kunci (20 Hari):</b>\n" + "\n".join(sr_lines)) if sr_lines else ""

    ma_section = ("\n" + "\n".join(ma_lines)) if ma_lines else ""

    return (
        f"📊 <b>Analisis Teknikal: {symbol}</b>\n"
        f"Harga Terkini: <b>{price_str}</b>\n"
        f"Sampel Data: <i>{ta.data_points} hari bursa</i>\n\n"
        f"📈 <b>Indikator Momentum & Tren:</b>\n"
        f"{rsi_line}"
        f"{ma_section}\n"
        f"• Tren: {trend_str}"
        f"{crossover_line}"
        f"{sr_section}\n\n"
        f"<i>⚠️ Indikator dihitung murni berbasis rumus matematika historis. Bukan ajakan jual/beli.</i>"
    )



