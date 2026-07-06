"""
Tests for production secret hardening (prompt 01):
  - password strength policy
  - JWT secret / seed password validation (fail-fast in production, warn in dev)
  - __DEV_MODE__ auth bypass rejected outside dev
"""

import logging

import pytest
from pydantic import ValidationError

from app.config import (
    Settings,
    production_secret_issues,
    validate_production_secrets,
)
from app.exceptions import ValidationException
from app.services.auth_service import (
    PASSWORD_MIN_LENGTH,
    password_strength_errors,
    validate_password_strength,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_settings(**overrides) -> Settings:
    base = dict(
        DATABASE_URL="sqlite+aiosqlite:///test.db",
        TELEGRAM_BOT_TOKEN="test-token",
        APP_URL="http://localhost:3000",
        ADMIN_API_KEY="key",
        JWT_SECRET_KEY="x" * 40,
        SEED_ADMIN_PASSWORD="strongpass1",
        ENVIRONMENT="production",
        # Pin explicitly so the conftest-wide DEV_AUTH_BYPASS_ENABLED=true env
        # var doesn't leak into these non-dev Settings and trip the validator.
        DEV_AUTH_BYPASS_ENABLED=False,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


# ── password strength ──────────────────────────────────────────────────────────

def test_password_too_short():
    errors = password_strength_errors("ab1")
    assert any(str(PASSWORD_MIN_LENGTH) in e for e in errors)


def test_password_no_digit():
    assert password_strength_errors("abcdefghij") != []


def test_password_no_letter():
    assert password_strength_errors("1234567890") != []


def test_password_valid():
    assert password_strength_errors("abcd123456") == []


def test_validate_password_strength_raises_on_weak():
    with pytest.raises(ValidationException):
        validate_password_strength("short")


def test_validate_password_strength_ok():
    # Should not raise.
    validate_password_strength("abcd123456")


# ── fail-closed ENVIRONMENT default ─────────────────────────────────────────────

def test_environment_defaults_to_production(monkeypatch):
    """Missing ENVIRONMENT → production (fail-closed)."""
    # Drop the conftest-wide dev env so we observe the real default.
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DEV_AUTH_BYPASS_ENABLED", raising=False)
    settings = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+aiosqlite:///test.db",
        TELEGRAM_BOT_TOKEN="test-token",
        APP_URL="http://localhost:3000",
        ADMIN_API_KEY="key",
        JWT_SECRET_KEY="x" * 40,
    )
    assert settings.ENVIRONMENT == "production"


def test_staging_fails_fast_on_weak_secret():
    """Any non-dev environment (incl. staging/typo) rejects weak secrets."""
    with pytest.raises(RuntimeError):
        validate_production_secrets(
            _make_settings(ENVIRONMENT="staging", JWT_SECRET_KEY="changeme")
        )


def test_dev_bypass_flag_outside_dev_refuses_to_boot():
    """DEV_AUTH_BYPASS_ENABLED combined with a non-dev env aborts startup."""
    with pytest.raises(ValidationError):
        _make_settings(ENVIRONMENT="production", DEV_AUTH_BYPASS_ENABLED=True)


# ── production secret validation ────────────────────────────────────────────────

def test_strong_secrets_no_issues():
    assert production_secret_issues(_make_settings()) == []


def test_short_jwt_secret_is_an_issue():
    issues = production_secret_issues(_make_settings(JWT_SECRET_KEY="short"))
    assert any("JWT_SECRET_KEY" in i for i in issues)


def test_demo_jwt_secret_is_an_issue():
    issues = production_secret_issues(
        _make_settings(JWT_SECRET_KEY="your-jwt-secret-key-change-in-production")
    )
    assert any("JWT_SECRET_KEY" in i for i in issues)


def test_weak_seed_password_is_an_issue():
    issues = production_secret_issues(_make_settings(SEED_ADMIN_PASSWORD="yosef"))
    assert any("SEED_ADMIN_PASSWORD" in i for i in issues)


def test_production_fails_fast_on_weak_secret():
    with pytest.raises(RuntimeError):
        validate_production_secrets(_make_settings(JWT_SECRET_KEY="changeme"))


def test_dev_only_warns_on_weak_secret(caplog):
    settings = _make_settings(ENVIRONMENT="dev", JWT_SECRET_KEY="changeme")
    with caplog.at_level(logging.WARNING, logger="ilutzim"):
        validate_production_secrets(settings)  # must NOT raise
    assert any("JWT_SECRET_KEY" in r.message for r in caplog.records)


def test_production_passes_with_strong_secrets():
    # Must not raise.
    validate_production_secrets(_make_settings())


# ── __DEV_MODE__ bypass gating ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dev_mode_bypass_rejected_in_production():
    """In production, the __DEV_MODE__ literal is treated as invalid Telegram
    data and rejected with 401 (no auth bypass)."""
    from fastapi import HTTPException

    from app.dependencies import get_current_user

    class _StubSettingsService:
        async def get_effective_bot_token(self):
            return "some-bot-token"

    class _StubUserRepo:
        async def get_active_users(self):  # would be hit if bypass were active
            raise AssertionError("dev bypass must not run in production")

        async def get_by_telegram_id(self, _tid):
            return None

    with pytest.raises(HTTPException) as exc:
        await get_current_user(
            x_telegram_init_data="__DEV_MODE__",
            settings=_make_settings(ENVIRONMENT="production"),
            user_repo=_StubUserRepo(),
            settings_service=_StubSettingsService(),
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_dev_mode_bypass_active_in_dev():
    """In dev WITH the opt-in flag, __DEV_MODE__ returns the first active user."""
    from app.dependencies import get_current_user

    sentinel = object()

    class _StubSettingsService:
        async def get_effective_bot_token(self):
            raise AssertionError("dev bypass should short-circuit before token")

    class _StubUserRepo:
        async def get_active_users(self):
            return [sentinel]

    result = await get_current_user(
        x_telegram_init_data="__DEV_MODE__",
        settings=_make_settings(ENVIRONMENT="dev", DEV_AUTH_BYPASS_ENABLED=True),
        user_repo=_StubUserRepo(),
        settings_service=_StubSettingsService(),
    )
    assert result is sentinel


@pytest.mark.asyncio
async def test_dev_mode_bypass_rejected_in_dev_without_flag():
    """In dev WITHOUT DEV_AUTH_BYPASS_ENABLED, __DEV_MODE__ is rejected 401 —
    the bypass can no longer be triggered by accident."""
    from fastapi import HTTPException

    from app.dependencies import get_current_user

    class _StubSettingsService:
        async def get_effective_bot_token(self):
            return "some-bot-token"

    class _StubUserRepo:
        async def get_active_users(self):
            raise AssertionError("dev bypass must not run without the flag")

        async def get_by_telegram_id(self, _tid):
            return None

    with pytest.raises(HTTPException) as exc:
        await get_current_user(
            x_telegram_init_data="__DEV_MODE__",
            settings=_make_settings(ENVIRONMENT="dev", DEV_AUTH_BYPASS_ENABLED=False),
            user_repo=_StubUserRepo(),
            settings_service=_StubSettingsService(),
        )
    assert exc.value.status_code == 401
