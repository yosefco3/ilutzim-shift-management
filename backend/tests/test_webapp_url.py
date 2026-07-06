"""Tests for the cache-busting guard WebApp URL.

Telegram's WebView caches the WebApp by URL, so guards could be served a stale
version of the form. The URL must carry a ``v`` version token (so it changes on
each deploy) and the bot keyboards must use it.
"""

from unittest.mock import patch

from app.bot.webapp import submit_webapp_url
from app.bot.keyboards.inline_kb import submission_success_kb, submit_constraints_kb


class TestSubmitWebappUrl:
    def test_includes_version_param(self):
        with patch("app.config.settings") as s, patch(
            "app.bot.webapp.APP_VERSION", "12345"
        ):
            s.APP_URL = "https://app.example.com"
            url = submit_webapp_url()
        assert url == "https://app.example.com/submit?v=12345"

    def test_includes_tg_id_and_version(self):
        with patch("app.config.settings") as s, patch(
            "app.bot.webapp.APP_VERSION", "999"
        ):
            s.APP_URL = "https://app.example.com"
            url = submit_webapp_url(tg_id=42)
        assert url == "https://app.example.com/submit?tg_id=42&v=999"


class TestKeyboardsUseVersionedUrl:
    def test_submit_constraints_kb_webapp_url_is_versioned(self):
        with patch("app.config.settings") as s, patch(
            "app.bot.webapp.APP_VERSION", "abc"
        ):
            s.APP_URL = "https://app.example.com"
            kb = submit_constraints_kb()
        url = kb.inline_keyboard[0][0].web_app.url
        assert "v=abc" in url
        assert url.startswith("https://app.example.com/submit")

    def test_submission_success_kb_webapp_url_is_versioned(self):
        with patch("app.config.settings") as s, patch(
            "app.bot.webapp.APP_VERSION", "abc"
        ):
            s.APP_URL = "https://app.example.com"
            kb = submission_success_kb()
        url = kb.inline_keyboard[0][0].web_app.url
        assert "v=abc" in url
