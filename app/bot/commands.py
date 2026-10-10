"""
MarketPulse — app/bot/commands.py
Telegram command handlers.
Handler tidak boleh berisi logika provider secara langsung.
Semua pengambilan data melalui MarketDataService.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal, InvalidOperation
from typing import FrozenSet, Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import (
    format_access_denied,
    format_add_exists,
    format_add_limit_reached,
    format_add_success,
    format_alert_created,
    format_alert_deleted,
    format_alert_limit_reached,
    format_alert_not_found,
    format_alerts_empty,
    format_alerts_list,
    format_help_message,
    format_market_summary,
    format_quote,
    format_remove_not_found,
    format_remove_success,
    format_start_message,
    format_watchlist,
    format_watchlist_empty,
)
from app.market_data.service import MarketDataService
from app.storage.alert_repository import AlertRepository
from app.storage.models import AlertCondition, AlertStatus
from app.storage.watchlist_repository import WatchlistRepository

logger = logging.getLogger(__name__)


def _is_allowed(user_id: int, allowed_ids: FrozenSet[int]) -> bool:
    """
    Cek apakah user diizinkan menggunakan bot.
    Fail-closed: jika allowed_ids kosong, semua akses ditolak.
    """
    if not allowed_ids:
        return False
    return user_id in allowed_ids


async def _check_access(
    update: Update,
    allowed_ids: FrozenSet[int],
) -> bool:
    """
    Cek akses dan kirim pesan penolakan jika tidak diizinkan.
    Return True jika akses diizinkan, False jika ditolak.
    Mencatat percobaan akses tidak sah di log tanpa stack trace.
    """
    if update.effective_user is None or update.message is None:
        return False

    user_id = update.effective_user.id
    if not _is_allowed(user_id, allowed_ids):
        logger.warning(
            "Akses ditolak untuk user_id=%d username=%s",
            user_id,
            update.effective_user.username or "unknown",
        )
        await update.message.reply_text(
            format_access_denied(),
            parse_mode=ParseMode.HTML,
        )
        return False

    return True


class BotCommandHandlers:
    """
    Kumpulan Telegram command handlers.
    Menerima dependencies via constructor (dependency injection).
    """

    def __init__(
        self,
        market_service: MarketDataService,
        allowed_ids: FrozenSet[int],
        watchlist_repo: Optional[WatchlistRepository] = None,
        max_watchlist_assets: int = 30,
        alert_repo: Optional[AlertRepository] = None,
        max_active_alerts: int = 50,
    ) -> None:
        self._market = market_service
        self._allowed_ids = allowed_ids
        self._watchlist_repo = watchlist_repo
        self._max_watchlist_assets = max_watchlist_assets
        self._alert_repo = alert_repo
        self._max_active_alerts = max_active_alerts

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler untuk /start"""
        if update.message is None:
            return

        if not await _check_access(update, self._allowed_ids):
            return

        await update.message.reply_text(
            format_start_message(),
            parse_mode=ParseMode.HTML,
        )
        logger.info("User %d menjalankan /start", update.effective_user.id)  # type: ignore[union-attr]

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler untuk /help"""
        if update.message is None:
            return

        if not await _check_access(update, self._allowed_ids):
            return

        await update.message.reply_text(
            format_help_message(),
            parse_mode=ParseMode.HTML,
        )
        logger.info("User %d menjalankan /help", update.effective_user.id)  # type: ignore[union-attr]

    async def cmd_stock(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handler untuk /stock <ticker>
        Contoh: /stock AAPL, /stock BBCA.JK
        """
        if update.message is None:
            return

        if not await _check_access(update, self._allowed_ids):
            return

        user_id = update.effective_user.id  # type: ignore[union-attr]

        # Validasi argumen
        if not context.args:
            await update.message.reply_text(
                "❓ Penggunaan: <code>/stock &lt;ticker&gt;</code>\n\n"
                "Contoh:\n"
                "<code>/stock AAPL</code>\n"
                "<code>/stock BBCA.JK</code>\n"
                "<code>/stock GOOGL</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        symbol = context.args[0].strip().upper()

        # Validasi panjang dan karakter dasar
        if not symbol or len(symbol) > 20:
            await update.message.reply_text(
                f"❌ Simbol <b>{symbol[:20]}</b> tidak valid. "
                "Simbol harus antara 1-20 karakter.",
                parse_mode=ParseMode.HTML,
            )
            return

        logger.info("User %d meminta quote untuk %s", user_id, symbol)

        # Kirim pesan "sedang memuat" untuk UX yang lebih baik
        loading_msg = await update.message.reply_text(
            f"⏳ Mengambil data untuk <b>{symbol}</b>...",
            parse_mode=ParseMode.HTML,
        )

        try:
            quote = await self._market.get_quote(symbol)
            message = format_quote(quote)
        except Exception as exc:
            # Safety net — MarketDataService seharusnya tidak raise ke sini
            logger.error("Unexpected error di cmd_stock untuk %s: %s", symbol, type(exc).__name__)
            message = (
                f"⚠️ Terjadi kesalahan tak terduga saat memproses <b>{symbol}</b>.\n"
                "Coba lagi beberapa saat."
            )

        # Edit pesan loading dengan hasil
        try:
            await loading_msg.edit_text(message, parse_mode=ParseMode.HTML)
        except Exception:
            # Fallback: kirim pesan baru jika edit gagal
            await update.message.reply_text(message, parse_mode=ParseMode.HTML)

    async def cmd_gold(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handler untuk /gold
        Mengambil harga emas futures COMEX (GC=F).
        Menampilkan label yang jelas bahwa ini adalah futures, bukan spot.
        """
        if update.message is None:
            return

        if not await _check_access(update, self._allowed_ids):
            return

        user_id = update.effective_user.id  # type: ignore[union-attr]
        logger.info("User %d meminta quote emas (GC=F)", user_id)

        loading_msg = await update.message.reply_text(
            "⏳ Mengambil data harga emas futures...",
            parse_mode=ParseMode.HTML,
        )

        try:
            quote = await self._market.get_gold_quote()
            message = format_quote(quote)
        except Exception as exc:
            logger.error("Unexpected error di cmd_gold: %s", type(exc).__name__)
            message = (
                "⚠️ Terjadi kesalahan tak terduga saat mengambil data emas.\n"
                "Coba lagi beberapa saat."
            )

        try:
            await loading_msg.edit_text(message, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(message, parse_mode=ParseMode.HTML)

    async def cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handler untuk /watchlist
        Menampilkan daftar seluruh aset yang dipantau oleh user beserta harga terkini.
        """
        if update.message is None:
            return

        if not await _check_access(update, self._allowed_ids):
            return

        user_id = update.effective_user.id  # type: ignore[union-attr]

        if self._watchlist_repo is None:
            await update.message.reply_text("⚠️ Fitur watchlist belum aktif.", parse_mode=ParseMode.HTML)
            return

        items = await self._watchlist_repo.get_user_watchlist(user_id)
        if not items:
            await update.message.reply_text(format_watchlist_empty(), parse_mode=ParseMode.HTML)
            return

        loading_msg = await update.message.reply_text(
            f"⏳ Mengambil harga terkini untuk {len(items)} aset...",
            parse_mode=ParseMode.HTML,
        )

        try:
            # Ambil quote secara konkuren untuk semua item
            tasks = [self._market.get_quote(item.symbol) for item in items]
            quotes = await asyncio.gather(*tasks, return_exceptions=False)
            items_with_quotes = list(zip(items, quotes))
            text = format_watchlist(items_with_quotes)
        except Exception as exc:
            logger.error("Error mengambil quotes watchlist untuk user %d: %s", user_id, type(exc).__name__)
            text = "⚠️ Terjadi kesalahan saat memuat data watchlist. Silakan coba lagi."

        try:
            await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_market(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handler untuk /market
        Snapshot ringkasan pergerakan harga pasar untuk seluruh aset di watchlist user.
        """
        if update.message is None:
            return

        if not await _check_access(update, self._allowed_ids):
            return

        user_id = update.effective_user.id  # type: ignore[union-attr]

        if self._watchlist_repo is None:
            await update.message.reply_text("⚠️ Fitur watchlist belum aktif.", parse_mode=ParseMode.HTML)
            return

        items = await self._watchlist_repo.get_user_watchlist(user_id)
        if not items:
            await update.message.reply_text(format_watchlist_empty(), parse_mode=ParseMode.HTML)
            return

        loading_msg = await update.message.reply_text(
            "⏳ Menyiapkan snapshot pasar...",
            parse_mode=ParseMode.HTML,
        )

        try:
            tasks = [self._market.get_quote(item.symbol) for item in items]
            quotes = await asyncio.gather(*tasks, return_exceptions=False)
            text = format_market_summary(quotes)
        except Exception as exc:
            logger.error("Error snapshot market untuk user %d: %s", user_id, type(exc).__name__)
            text = "⚠️ Terjadi kesalahan saat memuat snapshot pasar. Silakan coba lagi."

        try:
            await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handler untuk /add <ticker> [catatan]
        Menambahkan aset ke watchlist setelah memverifikasi simbol valid di market.
        """
        if update.message is None:
            return

        if not await _check_access(update, self._allowed_ids):
            return

        user_id = update.effective_user.id  # type: ignore[union-attr]

        if self._watchlist_repo is None:
            await update.message.reply_text("⚠️ Fitur watchlist belum aktif.", parse_mode=ParseMode.HTML)
            return

        if not context.args:
            await update.message.reply_text(
                "❓ Penggunaan: <code>/add &lt;ticker&gt; [catatan opsional]</code>\n\n"
                "Contoh:\n"
                "<code>/add BBCA.JK Core perbankan</code>\n"
                "<code>/add AAPL Saham teknologi</code>\n"
                "<code>/add GC=F Emas COMEX</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        symbol = context.args[0].strip().upper()
        note = " ".join(context.args[1:]).strip() if len(context.args) > 1 else None

        if not symbol or len(symbol) > 20:
            await update.message.reply_text(
                f"❌ Simbol <b>{symbol[:20]}</b> tidak valid. Panjang harus 1-20 karakter.",
                parse_mode=ParseMode.HTML,
            )
            return

        # Cek batas maksimal watchlist
        count = await self._watchlist_repo.count_user_watchlist(user_id)
        if count >= self._max_watchlist_assets:
            await update.message.reply_text(
                format_add_limit_reached(self._max_watchlist_assets),
                parse_mode=ParseMode.HTML,
            )
            return

        # Cek apakah sudah ada di watchlist
        if await self._watchlist_repo.is_in_watchlist(user_id, symbol):
            await update.message.reply_text(format_add_exists(symbol), parse_mode=ParseMode.HTML)
            return

        loading_msg = await update.message.reply_text(
            f"⏳ Memvalidasi simbol <b>{symbol}</b> di pasar...",
            parse_mode=ParseMode.HTML,
        )

        # Validasi simbol ke market provider
        quote = await self._market.get_quote(symbol)
        if quote.is_failed or not quote.has_price:
            await loading_msg.edit_text(
                f"❌ Simbol <b>{symbol}</b> tidak ditemukan atau data harga tidak tersedia.\n"
                "Pastikan format kode benar (contoh: <code>BBCA.JK</code> untuk IDX).",
                parse_mode=ParseMode.HTML,
            )
            return

        # Simpan ke database
        success, status = await self._watchlist_repo.add_item(user_id, symbol, note)
        if success:
            await loading_msg.edit_text(
                format_add_success(symbol, quote, note),
                parse_mode=ParseMode.HTML,
            )
        else:
            await loading_msg.edit_text(format_add_exists(symbol), parse_mode=ParseMode.HTML)

    async def cmd_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handler untuk /remove <ticker>
        Menghapus aset dari watchlist user.
        """
        if update.message is None:
            return

        if not await _check_access(update, self._allowed_ids):
            return

        user_id = update.effective_user.id  # type: ignore[union-attr]

        if self._watchlist_repo is None:
            await update.message.reply_text("⚠️ Fitur watchlist belum aktif.", parse_mode=ParseMode.HTML)
            return

        if not context.args:
            await update.message.reply_text(
                "❓ Penggunaan: <code>/remove &lt;ticker&gt;</code>\n\n"
                "Contoh: <code>/remove BBCA.JK</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        symbol = context.args[0].strip().upper()
        deleted = await self._watchlist_repo.remove_item(user_id, symbol)

        if deleted:
            await update.message.reply_text(format_remove_success(symbol), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(format_remove_not_found(symbol), parse_mode=ParseMode.HTML)

    async def cmd_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handler untuk /alert <ticker> <above|below> <target> [catatan]
        Contoh:
        /alert BBCA.JK above 6200
        /alert AAPL below 220 Entry point
        """
        if update.message is None:
            return

        if not await _check_access(update, self._allowed_ids):
            return

        user_id = update.effective_user.id  # type: ignore[union-attr]

        if self._alert_repo is None:
            await update.message.reply_text("⚠️ Fitur alert belum aktif.", parse_mode=ParseMode.HTML)
            return

        if not context.args or len(context.args) < 3:
            await update.message.reply_text(
                "❓ Penggunaan: <code>/alert &lt;ticker&gt; &lt;above|below&gt; &lt;target_harga&gt; [catatan]</code>\n\n"
                "<b>Contoh:</b>\n"
                "• <code>/alert BBCA.JK above 6200</code> — Alert saat BCA ≥ 6200\n"
                "• <code>/alert AAPL below 220 Target beli</code> — Alert saat Apple ≤ 220\n"
                "• <code>/alert GC=F above 2750</code> — Alert emas COMEX ≥ 2750",
                parse_mode=ParseMode.HTML,
            )
            return

        symbol = context.args[0].strip().upper()
        condition_raw = context.args[1].strip().lower()
        target_str = context.args[2].strip().replace(",", "")
        note = " ".join(context.args[3:]).strip() if len(context.args) > 3 else None

        if condition_raw not in ("above", "below"):
            await update.message.reply_text(
                "❌ Kondisi harus <code>above</code> (naik di atas) atau <code>below</code> (turun di bawah).\n"
                "Contoh: <code>/alert BBCA.JK above 6200</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        try:
            target_value = Decimal(target_str)
            if target_value <= 0:
                raise ValueError("Target harus positif")
        except (InvalidOperation, ValueError):
            await update.message.reply_text(
                f"❌ Nilai target harga '<b>{target_str}</b>' tidak valid. Masukkan angka positif.",
                parse_mode=ParseMode.HTML,
            )
            return

        # Cek batas kuota alert aktif
        active_count = await self._alert_repo.count_user_active_alerts(user_id)
        if active_count >= self._max_active_alerts:
            await update.message.reply_text(
                format_alert_limit_reached(self._max_active_alerts),
                parse_mode=ParseMode.HTML,
            )
            return

        loading_msg = await update.message.reply_text(
            f"⏳ Memvalidasi simbol <b>{symbol}</b> di pasar...",
            parse_mode=ParseMode.HTML,
        )

        # Validasi simbol ke provider pasar
        quote = await self._market.get_quote(symbol)
        if quote.is_failed or not quote.has_price:
            await loading_msg.edit_text(
                f"❌ Simbol <b>{symbol}</b> tidak ditemukan atau data harga tidak tersedia.\n"
                "Pastikan format kode benar (contoh: <code>BBCA.JK</code> untuk IDX).",
                parse_mode=ParseMode.HTML,
            )
            return

        # Simpan alert ke database
        try:
            alert = await self._alert_repo.create_alert(
                user_id=user_id,
                symbol=symbol,
                condition=condition_raw,
                target_value=target_value,
                note=note,
            )
            await loading_msg.edit_text(
                format_alert_created(alert.id, symbol, condition_raw, target_value, quote),
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            logger.error("Gagal membuat alert untuk user %d: %s", user_id, exc)
            await loading_msg.edit_text("⚠️ Terjadi kesalahan saat menyimpan alert. Coba lagi beberapa saat.", parse_mode=ParseMode.HTML)

    async def cmd_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handler untuk /alerts
        Menampilkan daftar seluruh alert aktif milik user.
        """
        if update.message is None:
            return

        if not await _check_access(update, self._allowed_ids):
            return

        user_id = update.effective_user.id  # type: ignore[union-attr]

        if self._alert_repo is None:
            await update.message.reply_text("⚠️ Fitur alert belum aktif.", parse_mode=ParseMode.HTML)
            return

        alerts = await self._alert_repo.get_user_alerts(user_id, status=AlertStatus.ACTIVE.value)
        await update.message.reply_text(
            format_alerts_list(alerts),
            parse_mode=ParseMode.HTML,
        )

    async def cmd_delalert(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handler untuk /delalert <id>
        Menghapus alert berdasarkan ID.
        """
        if update.message is None:
            return

        if not await _check_access(update, self._allowed_ids):
            return

        user_id = update.effective_user.id  # type: ignore[union-attr]

        if self._alert_repo is None:
            await update.message.reply_text("⚠️ Fitur alert belum aktif.", parse_mode=ParseMode.HTML)
            return

        if not context.args:
            await update.message.reply_text(
                "❓ Penggunaan: <code>/delalert &lt;id_alert&gt;</code>\n\n"
                "Contoh: <code>/delalert 1</code>\n"
                "Gunakan <code>/alerts</code> untuk melihat ID alert Anda.",
                parse_mode=ParseMode.HTML,
            )
            return

        id_str = context.args[0].strip()
        try:
            alert_id = int(id_str)
        except ValueError:
            await update.message.reply_text(
                f"❌ ID alert harus berupa angka bulat. Diberikan: <code>{id_str}</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        deleted = await self._alert_repo.delete_alert(user_id, alert_id)
        if deleted:
            await update.message.reply_text(format_alert_deleted(alert_id), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(format_alert_not_found(alert_id), parse_mode=ParseMode.HTML)


