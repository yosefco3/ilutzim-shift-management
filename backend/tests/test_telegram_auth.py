"""Tests for Telegram WebApp init_data validation, including replay/freshness.

Covers the security hardening:
  * HMAC validation accepts genuine init_data and rejects tampered data.
  * Stale init_data (old ``auth_date``) is rejected even with a valid HMAC.
  * The ``__DEV_MODE__`` bypass in get_current_user is gated to ENVIRONMENT=='dev'.
"""

import hashlib
import hmac
import json
import time
import urllib.parse

import pytest
from fastapi import HTTPException

from app.utils.telegram_auth import (
    validate_telegram_web_app_data,
    get_telegram_user_id,
)

BOT_TOKEN = "123456:TEST-bot-token"


def _build_init_data(auth_date: int, user_id: int = 42) -> str:
    """Build a correctly-signed init_data string for BOT_TOKEN."""
    fields = {
        "auth_date": str(auth_date),
        "user": json.dumps({"id": user_id, "first_name": "Test"}),
        "query_id": "AAA",
    }
    data_check_string = "\n".join(
        f"{k}={fields[k]}" for k in sorted(fields.keys())
    )
    secret_key = hmac.new(
        "WebAppData".encode(), BOT_TOKEN.encode(), hashlib.sha256
    ).digest()
    h = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    fields["hash"] = h
    return urllib.parse.urlencode(fields)


class TestTelegramAuthValidation:
    def test_fresh_init_data_is_valid(self):
        init_data = _build_init_data(int(time.time()))
        result = validate_telegram_web_app_data(init_data, BOT_TOKEN)
        assert result is not None
        assert get_telegram_user_id(init_data, BOT_TOKEN) == "42"

    def test_tampered_hash_rejected(self):
        init_data = _build_init_data(int(time.time())) + "&injected=evil"
        assert validate_telegram_web_app_data(init_data, BOT_TOKEN) is None

    def test_wrong_bot_token_rejected(self):
        init_data = _build_init_data(int(time.time()))
        assert validate_telegram_web_app_data(init_data, "999:other") is None

    def test_stale_init_data_rejected(self):
        """A perfectly-signed payload older than max_age is still rejected."""
        old = int(time.time()) - (25 * 60 * 60)  # 25h ago
        init_data = _build_init_data(old)
        assert validate_telegram_web_app_data(init_data, BOT_TOKEN) is None
        # ...but valid within a generous window
        assert (
            validate_telegram_web_app_data(
                init_data, BOT_TOKEN, max_age_seconds=48 * 60 * 60
            )
            is not None
        )

    def test_freshness_check_disabled(self):
        old = int(time.time()) - (10 * 24 * 60 * 60)
        init_data = _build_init_data(old)
        assert (
            validate_telegram_web_app_data(init_data, BOT_TOKEN, max_age_seconds=0)
            is not None
        )

    def test_missing_auth_date_rejected(self):
        """No auth_date → cannot prove freshness → rejected."""
        secret_key = hmac.new(
            "WebAppData".encode(), BOT_TOKEN.encode(), hashlib.sha256
        ).digest()
        fields = {"user": json.dumps({"id": 7})}
        dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
        fields["hash"] = hmac.new(
            secret_key, dcs.encode(), hashlib.sha256
        ).hexdigest()
        init_data = urllib.parse.urlencode(fields)
        assert validate_telegram_web_app_data(init_data, BOT_TOKEN) is None


class TestDevModeGating:
    """__DEV_MODE__ must only bypass auth when ENVIRONMENT == 'dev'."""

    @pytest.mark.asyncio
    async def test_dev_mode_blocked_in_production(self):
        from unittest.mock import AsyncMock
        from app.dependencies import get_current_user

        settings = type("S", (), {"ENVIRONMENT": "production", "DEV_AUTH_BYPASS_ENABLED": False, "TELEGRAM_BOT_TOKEN": BOT_TOKEN})()
        user_repo = AsyncMock()
        settings_service = AsyncMock()
        settings_service.get_effective_bot_token.return_value = BOT_TOKEN

        with pytest.raises(HTTPException) as exc:
            await get_current_user(
                x_telegram_init_data="__DEV_MODE__",
                settings=settings,
                user_repo=user_repo,
                settings_service=settings_service,
            )
        assert exc.value.status_code == 401
        user_repo.get_active_users.assert_not_called()

    @pytest.mark.asyncio
    async def test_dev_mode_allowed_in_dev(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.dependencies import get_current_user

        settings = type("S", (), {"ENVIRONMENT": "dev", "DEV_AUTH_BYPASS_ENABLED": True, "TELEGRAM_BOT_TOKEN": BOT_TOKEN})()
        fake_user = MagicMock()
        user_repo = AsyncMock()
        user_repo.get_active_users.return_value = [fake_user]

        result = await get_current_user(
            x_telegram_init_data="__DEV_MODE__",
            settings=settings,
            user_repo=user_repo,
        )
        assert result is fake_user
