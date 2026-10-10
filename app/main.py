"""
MarketPulse — app/main.py
Entry point aplikasi.
Setup logging, konfigurasi, dan jalankan Telegram bot.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from telegram.ext import ApplicationBuilder, CommandHandler

from app.config import get_settings
from app.market_data.providers.yfinance_provider import YFinanceProvider
from app.market_data.service import MarketDataService
from app.bot.commands import BotCommandHandlers


def setup_logging(log_level: str) -> None:
    """Setup logging yang aman — tidak mencetak secrets."""
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=getattr(logging, log_level, logging.INFO),
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Kurangi verbositas library eksternal
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main() -> None:
    """Main entry point."""
    settings = get_settings()
    setup_logging(settings.log_level)

    logger = logging.getLogger(__name__)
    logger.info("MarketPulse starting up... env=%s", settings.app_env)

    # Validasi konfigurasi kritis
    if not settings.is_token_configured():
        logger.critical(
            "TELEGRAM_BOT_TOKEN tidak dikonfigurasi. "
            "Set variabel di file .env dan restart bot."
        )
        sys.exit(1)

    allowed_ids = settings.get_allowed_user_ids()
    if not allowed_ids:
        logger.critical(
            "TELEGRAM_ALLOWED_USER_IDS tidak dikonfigurasi atau tidak valid. "
            "Bot berjalan dengan mode fail-closed (tidak ada akses)."
        )
        # Tidak exit — biarkan berjalan tapi akses ditolak. Berguna untuk deployment check.

    logger.info("Allowlist dikonfigurasi dengan %d user ID.", len(allowed_ids))

    # Buat direktori data jika belum ada
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    # Inisialisasi Database
    import asyncio
    from telegram.constants import ParseMode
    from app.alerts.engine import AlertEngine
    from app.bot.formatters import format_alert_triggered
    from app.storage.alert_repository import AlertRepository
    from app.storage.database import DatabaseManager
    from app.storage.models import AlertItem
    from app.storage.watchlist_repository import WatchlistRepository

    db_manager = DatabaseManager(database_url=settings.database_url)
    asyncio.run(db_manager.init_db())
    watchlist_repo = WatchlistRepository(session_factory=db_manager.session_factory)
    alert_repo = AlertRepository(session_factory=db_manager.session_factory)

    # Setup provider dan service
    provider = YFinanceProvider(timeout_seconds=settings.request_timeout_seconds)
    market_service = MarketDataService(
        provider=provider,
        cache_ttl_seconds=settings.quote_cache_seconds,
    )

    # Setup command handlers
    handlers = BotCommandHandlers(
        market_service=market_service,
        allowed_ids=allowed_ids,
        watchlist_repo=watchlist_repo,
        max_watchlist_assets=settings.max_watchlist_assets,
        alert_repo=alert_repo,
        max_active_alerts=settings.max_active_alerts,
    )

    # Build Telegram application
    builder = ApplicationBuilder().token(settings.telegram_bot_token)

    # Notification callback untuk AlertEngine
    async def on_alert_triggered(alert: AlertItem, quote: Any) -> None:
        try:
            text = format_alert_triggered(alert, quote)
            await app.bot.send_message(
                chat_id=alert.user_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            logger.error("Gagal mendispatch pesan alert ke user %d: %s", alert.user_id, exc)

    # Inisialisasi AlertEngine
    alert_engine = AlertEngine(
        alert_repo=alert_repo,
        market_service=market_service,
        notify_callback=on_alert_triggered,
        check_interval_seconds=settings.alert_check_interval_seconds,
    )

    async def post_init(application: Any) -> None:
        asyncio.create_task(alert_engine.start())
        logger.info("Background AlertEngine task berhasil dijalankan.")

    async def post_shutdown(application: Any) -> None:
        alert_engine.stop()
        await db_manager.close()
        logger.info("Background AlertEngine task dan koneksi database dihentikan.")

    app = builder.post_init(post_init).post_shutdown(post_shutdown).build()

    # Register commands
    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("stock", handlers.cmd_stock))
    app.add_handler(CommandHandler("gold", handlers.cmd_gold))
    app.add_handler(CommandHandler("watchlist", handlers.cmd_watchlist))
    app.add_handler(CommandHandler("market", handlers.cmd_market))
    app.add_handler(CommandHandler("add", handlers.cmd_add))
    app.add_handler(CommandHandler("remove", handlers.cmd_remove))
    app.add_handler(CommandHandler("alert", handlers.cmd_alert))
    app.add_handler(CommandHandler("alerts", handlers.cmd_alerts))
    app.add_handler(CommandHandler("delalert", handlers.cmd_delalert))

    logger.info(
        "Bot siap. Provider: %s. Timezone: %s",
        settings.market_provider,
        settings.app_timezone,
    )
    logger.info("Memulai polling...")

    # Jalankan bot (blocking)
    app.run_polling(
        allowed_updates=["message"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
