"""
MarketPulse — app/alerts/engine.py
Engine evaluasi alert dan background polling worker.
Memeriksa kondisi target harga, mengontrol cooldown, dan mendispatch notifikasi Telegram.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Coroutine, Optional

from app.domain.market_schemas import QuoteResult
from app.storage.models import AlertCondition, AlertItem, AlertStatus
from app.storage.alert_repository import AlertRepository
from app.market_data.service import MarketDataService

logger = logging.getLogger(__name__)


def evaluate_condition(
    condition: str,
    target_value: Decimal,
    quote: QuoteResult,
) -> bool:
    """
    Evaluasi apakah quote pasar saat ini memenuhi kriteria alert.
    Returns True jika kondisi tercapai, False jika tidak.
    """
    if not quote.has_price or quote.price is None:
        return False

    cond = condition.lower().strip()

    if cond == AlertCondition.ABOVE.value:
        return quote.price >= target_value

    if cond == AlertCondition.BELOW.value:
        return quote.price <= target_value

    if cond == AlertCondition.PCT_UP.value:
        if not quote.has_change or quote.price_change_pct is None:
            return False
        return quote.price_change_pct >= target_value

    if cond == AlertCondition.PCT_DOWN.value:
        if not quote.has_change or quote.price_change_pct is None:
            return False
        # target_value untuk penurunan bisa positif atau negatif dari input pengguna
        target_down = -abs(target_value)
        return quote.price_change_pct <= target_down

    return False


def is_in_cooldown(alert: AlertItem, now: datetime) -> bool:
    """
    Cek apakah alert masih dalam masa jeda (cooldown) sejak pemicu terakhir.
    Mencegah flooding notifikasi jika harga berosilasi di sekitar target.
    """
    if alert.last_triggered_at is None:
        return False

    last_ts = alert.last_triggered_at
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)

    elapsed_seconds = (now - last_ts).total_seconds()
    cooldown_seconds = alert.cooldown_minutes * 60
    return elapsed_seconds < cooldown_seconds


class AlertEngine:
    """
    Engine untuk memantau alert harga secara periodik di background.
    """

    def __init__(
        self,
        alert_repo: AlertRepository,
        market_service: MarketDataService,
        notify_callback: Optional[Callable[[AlertItem, QuoteResult], Coroutine[Any, Any, None]]] = None,
        check_interval_seconds: int = 120,
    ) -> None:
        self._alert_repo = alert_repo
        self._market = market_service
        self._notify_callback = notify_callback
        self._check_interval = check_interval_seconds
        self._stop_event = asyncio.Event()
        self._worker_task: Optional[asyncio.Task[None]] = None

    async def check_alerts_once(self) -> list[tuple[AlertItem, QuoteResult]]:
        """
        Menjalankan 1 siklus evaluasi semua alert aktif.
        Mengembalikan daftar alert yang berhasil terpicu beserta quotenya.
        """
        now = datetime.now(timezone.utc)
        active_alerts = await self._alert_repo.get_all_active_alerts()
        if not active_alerts:
            logger.debug("Tidak ada alert aktif untuk dievaluasi.")
            return []

        # Kumpulkan simbol unik untuk meminimalkan request ke provider data
        distinct_symbols = list({alert.symbol for alert in active_alerts})
        logger.debug("Mengevaluasi %d alert pada %d simbol...", len(active_alerts), len(distinct_symbols))

        # Ambil quotes secara konkuren dengan caching
        quote_results = await asyncio.gather(
            *[self._market.get_quote(sym) for sym in distinct_symbols],
            return_exceptions=True,
        )

        quotes_map: dict[str, QuoteResult] = {}
        for sym, res in zip(distinct_symbols, quote_results):
            if isinstance(res, QuoteResult) and not res.is_failed and res.has_price:
                quotes_map[sym] = res
            else:
                logger.debug("Gagal mengambil quote untuk simbol %s saat evaluasi alert", sym)

        triggered: list[tuple[AlertItem, QuoteResult]] = []

        for alert in active_alerts:
            quote = quotes_map.get(alert.symbol)
            if quote is None:
                continue

            # Cek apakah dalam cooldown
            if is_in_cooldown(alert, now):
                logger.debug("Alert #%d (%s) masih dalam cooldown.", alert.id, alert.symbol)
                continue

            # Evaluasi kondisi
            if evaluate_condition(alert.condition, alert.target_value, quote):
                logger.info(
                    "ALERT TERPICU! #%d: %s %s %s (Harga terkini: %s)",
                    alert.id, alert.symbol, alert.condition, alert.target_value, quote.price,
                )

                # Update database
                await self._alert_repo.mark_triggered(
                    alert.id,
                    triggered_at=now,
                    is_recurring=alert.is_recurring,
                )

                # Kirim notifikasi jika callback tersedia
                if self._notify_callback:
                    try:
                        await self._notify_callback(alert, quote)
                    except Exception as exc:
                        logger.error("Gagal mengirim notifikasi alert #%d: %s", alert.id, exc)

                triggered.append((alert, quote))

        return triggered

    async def start(self) -> None:
        """Memulai background worker loop."""
        self._stop_event.clear()
        logger.info("Memulai background AlertEngine worker (interval: %ds)...", self._check_interval)

        while not self._stop_event.is_set():
            try:
                await self.check_alerts_once()
            except Exception as exc:
                logger.error("Error tidak terduga pada siklus AlertEngine: %s", exc)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._check_interval)
            except asyncio.TimeoutError:
                pass

        logger.info("Background AlertEngine worker telah berhenti.")

    def stop(self) -> None:
        """Menghentikan background worker loop."""
        self._stop_event.set()
