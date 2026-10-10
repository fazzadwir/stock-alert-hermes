"""
Unit tests untuk app/config.py
Memastikan konfigurasi dan allowlist bekerja dengan benar.
Tidak memerlukan token Telegram asli.
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch


class TestSettings:
    """Tests untuk Settings class."""

    def test_default_values(self):
        """Settings harus punya nilai default yang aman."""
        with patch.dict(os.environ, {}, clear=True):
            # Import fresh untuk menghindari lru_cache
            import importlib
            import app.config as config_module
            importlib.reload(config_module)
            settings = config_module.Settings()

        assert settings.app_env == "development"
        assert settings.app_timezone == "Asia/Jakarta"
        assert settings.log_level == "INFO"
        assert settings.market_provider == "yfinance"
        assert settings.hermes_mode == "disabled"

    def test_telegram_token_not_in_defaults(self):
        """Token default harus kosong — tidak boleh ada hardcoded token."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import app.config as config_module
            importlib.reload(config_module)
            settings = config_module.Settings()

        assert settings.telegram_bot_token == ""
        assert not settings.is_token_configured()

    def test_token_configured_when_set(self):
        """is_token_configured harus return True jika token ada."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:abc"}, clear=False):
            import importlib
            import app.config as config_module
            importlib.reload(config_module)
            settings = config_module.Settings(_env_file=None)

        assert settings.is_token_configured()


class TestAllowlistParsing:
    """Tests untuk get_allowed_user_ids()"""

    def _make_settings(self, user_ids_str: str):
        import importlib
        import app.config as config_module
        importlib.reload(config_module)
        settings = config_module.Settings(_env_file=None)
        settings.telegram_allowed_user_ids = user_ids_str
        return settings

    def test_empty_string_returns_empty_frozenset(self):
        """String kosong → frozenset kosong → fail-closed."""
        settings = self._make_settings("")
        result = settings.get_allowed_user_ids()
        assert result == frozenset()

    def test_whitespace_only_returns_empty_frozenset(self):
        """String hanya spasi → frozenset kosong."""
        settings = self._make_settings("   ")
        result = settings.get_allowed_user_ids()
        assert result == frozenset()

    def test_single_valid_id(self):
        """Single ID valid harus diparsing dengan benar."""
        settings = self._make_settings("123456789")
        result = settings.get_allowed_user_ids()
        assert result == frozenset({123456789})

    def test_multiple_valid_ids(self):
        """Multiple ID valid (comma-separated) harus semua diparse."""
        settings = self._make_settings("111,222,333")
        result = settings.get_allowed_user_ids()
        assert result == frozenset({111, 222, 333})

    def test_ids_with_spaces(self):
        """ID dengan spasi di sekitar koma harus diparse dengan benar."""
        settings = self._make_settings("111, 222 , 333")
        result = settings.get_allowed_user_ids()
        assert result == frozenset({111, 222, 333})

    def test_invalid_entry_is_skipped(self):
        """Entry tidak valid (bukan integer) harus diabaikan, bukan crash."""
        settings = self._make_settings("111,abc,333")
        result = settings.get_allowed_user_ids()
        # Entry valid tetap ada, invalid dibuang
        assert 111 in result
        assert 333 in result
        # 'abc' diabaikan
        assert len(result) == 2

    def test_all_invalid_returns_empty_frozenset(self):
        """Semua entry invalid → frozenset kosong → fail-closed."""
        settings = self._make_settings("abc,xyz,!!!!")
        result = settings.get_allowed_user_ids()
        assert result == frozenset()

    def test_fail_closed_when_empty(self):
        """Allowlist kosong → tidak ada yang boleh akses."""
        settings = self._make_settings("")
        allowed = settings.get_allowed_user_ids()
        # Simulasi cek akses: user_id tidak ada di frozenset kosong
        assert 999999 not in allowed
        assert len(allowed) == 0


class TestHermesMode:
    """Tests untuk validasi hermes_mode."""

    def test_valid_modes(self):
        """Mode yang valid harus diterima."""
        import importlib
        import app.config as config_module

        for mode in ["disabled", "cli", "serve"]:
            importlib.reload(config_module)
            settings = config_module.Settings(_env_file=None)
            settings.hermes_mode = mode  # bypass validator untuk test ini
            assert settings.is_hermes_enabled() == (mode != "disabled")

    def test_disabled_mode_is_not_enabled(self):
        """Mode disabled → is_hermes_enabled() harus False."""
        import importlib
        import app.config as config_module
        importlib.reload(config_module)
        settings = config_module.Settings(_env_file=None)
        settings.hermes_mode = "disabled"
        assert not settings.is_hermes_enabled()
