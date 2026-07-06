"""
Tests for the Telegram bot package (Step 06).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import User as TgUser, Chat


# ── bot_instance ──────────────────────────────────────────

class TestBotInstance:
    """Tests for bot_instance singleton."""

    def test_get_bot_no_token_raises(self):
        """get_bot should raise if no token configured."""
        mock_settings = MagicMock()
        mock_settings.TELEGRAM_BOT_TOKEN = ""
        with patch("app.bot.bot_instance.get_settings", return_value=mock_settings):
            # Reset singleton
            import app.bot.bot_instance as mod
            mod._bot = None
            with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
                mod.get_bot()

    def test_get_bot_creates_singleton(self):
        """get_bot should return same Bot instance on repeated calls."""
        # aiogram validates token format (digits:alphanum), so use a valid-looking one
        mock_settings = MagicMock()
        mock_settings.TELEGRAM_BOT_TOKEN = "1234567890:AAHtesttokenvalidformat1234567890"
        with patch("app.bot.bot_instance.get_settings", return_value=mock_settings):
            import app.bot.bot_instance as mod
            mod._bot = None

            bot1 = mod.get_bot()
            bot2 = mod.get_bot()
            assert bot1 is bot2
            mod._bot = None


# ── keyboards ─────────────────────────────────────────────

class TestKeyboards:
    """Tests for inline keyboard builders."""

    def test_weekday_keyboard(self):
        from app.bot.keyboards.inline_kb import weekday_kb
        kb = weekday_kb("w-uuid")
        assert kb is not None
        assert kb.inline_keyboard is not None
        # 7 days + finish + back = 9 rows
        assert len(kb.inline_keyboard) == 9

    def test_main_menu_keyboard(self):
        from app.bot.keyboards.inline_kb import main_menu_kb
        kb = main_menu_kb()
        assert kb is not None
        # submit, status, help = 3 rows
        assert len(kb.inline_keyboard) == 3


# ── notifications ──────────────────────────────────────────

class TestNotifications:
    """Tests for notification helpers."""

    @pytest.mark.asyncio
    async def test_send_notification_no_bot(self):
        """send_notification should gracefully handle missing bot."""
        with patch("app.bot.notifications.get_bot", side_effect=Exception("no bot")):
            from app.bot.notifications import send_notification
            # Should not raise
            await send_notification(12345, "test message")

    @pytest.mark.asyncio
    async def test_broadcast_notifications(self):
        """broadcast_notifications should iterate over IDs."""
        with patch("app.bot.notifications.send_notification", new_callable=AsyncMock) as mock_send:
            from app.bot.notifications import broadcast_notifications
            await broadcast_notifications([111, 222], "hello")
            assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_send_photo_no_bot(self):
        """send_photo returns False (never raises) when the bot is unavailable."""
        with patch("app.bot.notifications.get_bot", return_value=None):
            from app.bot.notifications import send_photo
            assert await send_photo(12345, b"PNG", "s.png") is False

    @pytest.mark.asyncio
    async def test_send_photo_success(self):
        """send_photo delegates to bot.send_photo and returns True."""
        mock_bot = MagicMock()
        mock_bot.send_photo = AsyncMock()
        with patch("app.bot.notifications.get_bot", return_value=mock_bot):
            from app.bot.notifications import send_photo
            ok = await send_photo(12345, b"PNGBYTES", "s.png", caption="hi")
            assert ok is True
            mock_bot.send_photo.assert_awaited_once()


# ── bot_router ────────────────────────────────────────────

class TestBotRouter:
    """Tests for bot_router lifecycle functions."""

    @pytest.mark.asyncio
    async def test_get_dispatcher_creates_singleton(self):
        """get_dispatcher should return same Dispatcher instance."""
        import app.bot.bot_router as mod
        mod._dispatcher = None

        with patch("app.bot.bot_router.get_bot"):
            dp1 = mod.get_dispatcher()
            dp2 = mod.get_dispatcher()
            assert dp1 is dp2
            # Reset for other tests
            mod._dispatcher = None

    @pytest.mark.asyncio
    async def test_start_bot(self):
        """start_bot should start polling as background task."""
        mock_bot = AsyncMock()
        mock_dp = AsyncMock()

        with patch("app.bot.bot_router.get_bot", return_value=mock_bot), \
             patch("app.bot.bot_router.get_dispatcher", return_value=mock_dp):
            import app.bot.bot_router as mod

            await mod.start_bot()
            mock_bot.delete_webhook.assert_called_once()


# ── middlewares ───────────────────────────────────────────

class TestAuthMiddleware:
    """Tests for auth middleware."""

    @pytest.mark.asyncio
    async def test_middleware_passes_known_user(self):
        """AuthMiddleware should pass through known users."""
        from app.bot.middlewares.auth import AuthMiddleware

        mw = AuthMiddleware()
        handler = AsyncMock()
        event = MagicMock()
        event.from_user = MagicMock()
        event.from_user.id = 12345
        data = {}

        mock_pool = MagicMock()
        mock_user_svc = MagicMock()
        mock_user_svc.get_by_telegram_id = AsyncMock(return_value={"id": "user-uuid", "is_active": True})
        with patch("app.database.get_pool", return_value=mock_pool), \
             patch("app.services.user_service.UserService", return_value=mock_user_svc):
            await mw(handler, event, data)
            handler.assert_called_once()
