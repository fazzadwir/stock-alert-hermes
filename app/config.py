"""
MarketPulse — app/config.py
Konfigurasi aplikasi berbasis pydantic-settings.
Semua nilai dibaca dari environment variables / .env file.
TIDAK BOLEH mencetak atau log nilai secrets.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import FrozenSet

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Konfigurasi MarketPulse dari environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Application ─────────────────────────────────────────────────────────
    app_env: str = "development"
    app_timezone: str = "Asia/Jakarta"
    log_level: str = "INFO"

    # ─── Telegram ────────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_allowed_user_ids: str = ""  # comma-separated string

    # ─── Database ────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./data/marketpulse.db"

    # ─── Market Data ─────────────────────────────────────────────────────────
    market_provider: str = "yfinance"
    request_timeout_seconds: int = 15
    quote_cache_seconds: int = 60
    max_watchlist_assets: int = 30
    max_active_alerts: int = 50
    alert_check_interval_seconds: int = 120

    # ─── Hermes Agent ────────────────────────────────────────────────────────
    hermes_mode: str = "disabled"       # disabled | cli | serve
    hermes_command: str = "hermes"
    hermes_timeout_seconds: int = 60

    # ─── Computed ────────────────────────────────────────────────────────────
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level harus salah satu dari: {valid}")
        return upper

    @field_validator("hermes_mode")
    @classmethod
    def validate_hermes_mode(cls, v: str) -> str:
        valid = {"disabled", "cli", "serve"}
        lower = v.lower()
        if lower not in valid:
            raise ValueError(f"hermes_mode harus salah satu dari: {valid}")
        return lower

    @model_validator(mode="after")
    def validate_token_not_empty_in_production(self) -> "Settings":
        """Validasi: di production, token harus ada."""
        if self.app_env == "production" and not self.telegram_bot_token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN harus diset di production environment."
            )
        return self

    def get_allowed_user_ids(self) -> FrozenSet[int]:
        """
        Parse TELEGRAM_ALLOWED_USER_IDS menjadi frozenset of int.
        Return empty frozenset jika string kosong atau tidak valid.
        Fail-closed: jika tidak ada user yang valid, akses ditolak untuk semua.
        """
        if not self.telegram_allowed_user_ids.strip():
            return frozenset()

        result: set[int] = set()
        for part in self.telegram_allowed_user_ids.split(","):
            stripped = part.strip()
            if stripped:
                try:
                    result.add(int(stripped))
                except ValueError:
                    # Log warning tapi jangan crash; abaikan entry yang tidak valid
                    logging.getLogger(__name__).warning(
                        "TELEGRAM_ALLOWED_USER_IDS: entry tidak valid diabaikan (bukan integer)."
                    )
        return frozenset(result)

    def is_token_configured(self) -> bool:
        """Cek apakah Telegram token sudah dikonfigurasi."""
        return bool(self.telegram_bot_token.strip())

    def is_hermes_enabled(self) -> bool:
        """Cek apakah Hermes integration diaktifkan."""
        return self.hermes_mode != "disabled"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Singleton settings instance.
    Menggunakan lru_cache agar .env hanya dibaca sekali.
    """
    return Settings()
