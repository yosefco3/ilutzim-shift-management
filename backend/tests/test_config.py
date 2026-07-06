"""
Tests for configuration module.
"""

import os
import pytest

from app.config import get_settings, Settings


def test_settings_loads_from_env() -> None:
    """Settings should load from environment variables."""
    settings = get_settings()
    assert settings.ENVIRONMENT in ("dev", "staging", "production")
    assert settings.DATABASE_URL is not None
    assert settings.TELEGRAM_BOT_TOKEN is not None


def test_settings_caches_singleton() -> None:
    """get_settings should return the same instance on repeated calls."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_default_values(monkeypatch) -> None:
    """Default values should be set correctly."""
    # Remove env vars that may override defaults via pydantic-settings
    for key in ("LOG_LEVEL", "ENVIRONMENT", "DEV_AUTH_BYPASS_ENABLED",
                "DATABASE_URL", "TELEGRAM_BOT_TOKEN",
                "APP_URL", "ADMIN_API_KEY", "JWT_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(
        _env_file=None,  # prevent .env file from overriding defaults
        DATABASE_URL="sqlite+aiosqlite:///test.db",
        TELEGRAM_BOT_TOKEN="test",
        APP_URL="http://localhost:3000",
        ADMIN_API_KEY="key",
        JWT_SECRET_KEY="secret",
    )
    assert settings.ENVIRONMENT == "production"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.JWT_ALGORITHM == "HS256"
    assert settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 60


def test_settings_has_app_url():
    """Settings must include APP_URL after migration."""
    settings = get_settings()
    assert hasattr(settings, 'APP_URL')
    assert settings.APP_URL


def test_cors_origins_includes_app_url():
    """cors_origins must include APP_URL."""
    settings = get_settings()
    assert settings.APP_URL in settings.cors_origins


def test_cors_origins_dev_includes_localhost():
    """In dev mode, localhost:3001 should be in cors_origins."""
    settings = get_settings()
    if settings.ENVIRONMENT == "dev":
        assert "http://localhost:3001" in settings.cors_origins


def test_cors_origins_never_wildcard():
    """cors_origins must never include '*'."""
    settings = get_settings()
    assert "*" not in settings.cors_origins