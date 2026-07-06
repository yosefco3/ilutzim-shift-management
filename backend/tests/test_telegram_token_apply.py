"""Tests for the env-only Telegram bot token.

The token is sourced exclusively from the TELEGRAM_BOT_TOKEN environment
variable. It is never stored in or read from the DB, and there is no admin
endpoint to change it live.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.admin_settings_controller import router
from app.dependencies import get_settings_service, require_admin_role
from app.services.settings_service import SettingsService


def _make_app(svc):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings_service] = lambda: svc
    app.dependency_overrides[require_admin_role] = lambda: {"role": "admin"}
    return app


def test_no_telegram_apply_endpoint():
    """The live token-apply route must no longer exist (env-only token)."""
    svc = AsyncMock()
    client = TestClient(_make_app(svc))
    resp = client.post("/admin/settings/telegram/apply", json={"token": "123:abc"})
    assert resp.status_code in (404, 405)


@pytest.mark.asyncio
async def test_effective_token_comes_from_env(monkeypatch):
    repo = AsyncMock()
    import app.config

    monkeypatch.setattr(
        app.config, "get_settings", lambda: MagicMock(TELEGRAM_BOT_TOKEN="env-token")
    )
    assert await SettingsService(repo).get_effective_bot_token() == "env-token"
    # The token never touches the DB.
    repo.get.assert_not_called()


@pytest.mark.asyncio
async def test_effective_token_empty_when_env_unset(monkeypatch):
    repo = AsyncMock()
    import app.config

    monkeypatch.setattr(
        app.config, "get_settings", lambda: MagicMock(TELEGRAM_BOT_TOKEN="")
    )
    assert await SettingsService(repo).get_effective_bot_token() == ""
