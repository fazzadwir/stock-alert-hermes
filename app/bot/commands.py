"""
MarketPulse — app/bot/commands.py
Telegram command handlers.
Handler tidak boleh berisi logika provider secara langsung.
Semua pengambilan data melalui MarketDataService.
"""

from __future__ import annotations

import logging
from typing import FrozenSet

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.formatters import (
    format_access_denied,
    format_help_message,
    format_quote,
    format_start_message,
)
from app.market_data.service import MarketDataService

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
    Menerima MarketDataService dan allowed_ids via constructor (dependency injection).
    """

    def __init__(
        self,
        market_service: MarketDataService,
        allowed_ids: FrozenSet[int],
    ) -> None:
        self._market = market_service
        self._allowed_ids = allowed_ids

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
