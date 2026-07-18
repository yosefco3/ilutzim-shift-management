"""
Procedure card + WebApp read button — the short card that replaced the chunked
procedure broadcast, and the read (web_app) button on every procedures keyboard.

Covers: ``send_procedure_card`` sends ONE short HTML-escaped message with the
keyboard; the read button's web_app URL carries the procedure id AND the
cache-busting ``v=`` param; ``procedure_view_kb`` puts the read row first;
publish broadcast fans the card out with preserved ``{sent, skipped, total}``
accounting; ``on_view`` sends the card (no chunk loop); the reminder send
includes the keyboard; and the deleted chunk helpers leave no references behind.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot import notifications as notif
from app.bot.keyboards import procedures as kb
from app.bot.keyboards.procedures import (
    procedure_view_kb,
    read_procedure_button,
    retake_kb,
    start_quiz_kb,
)
from app.bot.webapp import procedure_webapp_url
from app.procedures.services.publish_service import RealProcedurePublisher


# ── procedure_webapp_url + read button ───────────────────────────────────────


def test_procedure_webapp_url_has_id_and_version():
    """The read button URL embeds the procedure id AND the v= cache-buster. [EDGE I2]"""
    url = procedure_webapp_url("abc-123")
    assert "/procedure/abc-123" in url
    assert "v=" in url


def test_read_procedure_button_is_web_app_with_url():
    btn = read_procedure_button("pid")
    assert btn.web_app is not None
    assert "/procedure/pid" in btn.web_app.url
    assert "v=" in btn.web_app.url
    assert btn.text == "📖 קרא נוהל"


def test_start_quiz_kb_has_read_row_first_then_quiz():
    """Read (web_app) row first, quiz (callback) row second; prefix unchanged. [EDGE B1]"""
    markup = start_quiz_kb("pid")
    rows = markup.inline_keyboard
    assert rows[0][0].text == "📖 קרא נוהל"
    assert rows[0][0].web_app is not None
    assert rows[1][0].text == "▶️ התחל מבחן"
    assert rows[1][0].callback_data == f"{kb.QUIZ_START_PREFIX}pid"


def test_retake_kb_has_read_row_first_then_retake():
    markup = retake_kb("pid")
    rows = markup.inline_keyboard
    assert rows[0][0].text == "📖 קרא נוהל"
    assert rows[1][0].callback_data == f"{kb.QUIZ_START_PREFIX}pid"


def test_procedure_view_kb_read_first_quiz_second_back_last():
    markup = procedure_view_kb("pid", passed=False)
    rows = markup.inline_keyboard
    assert rows[0][0].text == "📖 קרא נוהל"          # read row
    assert rows[1][0].text == "▶️ התחל מבחן"          # quiz row
    assert rows[1][0].callback_data == f"{kb.QUIZ_START_PREFIX}pid"
    assert rows[2][0].callback_data == kb.PROC_MENU_CB  # back to list


def test_procedure_view_kb_passed_marker():
    markup = procedure_view_kb("pid", passed=True)
    rows = markup.inline_keyboard
    assert rows[1][0].text == "✅ עברת — מבחן חוזר"


# ── send_procedure_card ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_procedure_card_one_short_message_with_keyboard(monkeypatch):
    """The card is a single short HTML message; title is escaped; the keyboard
    (with the web_app read row + quiz row) is attached."""
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    monkeypatch.setattr(notif, "get_bot", lambda: fake_bot)

    markup = start_quiz_kb("pid")
    ok = await notif.send_procedure_card(111, "כותרת <b>", reply_markup=markup)
    assert ok is True
    assert fake_bot.send_message.await_count == 1
    call = fake_bot.send_message.call_args
    text = call.kwargs["text"]
    assert len(text) < 600  # a short card, not a wall of text
    assert "📜" in text
    # title HTML-escaped (the bot parses the message as HTML)
    assert "&lt;b&gt;" in text
    assert "<b>כותרת &lt;b&gt;</b>" in text
    # one-line prompt present
    assert "📖 קרא נוהל" in text
    # keyboard attached, first row is the web_app read button
    rows = call.kwargs["reply_markup"].inline_keyboard
    assert rows[0][0].web_app is not None
    assert "v=" in rows[0][0].web_app.url
    assert "/procedure/pid" in rows[0][0].web_app.url


@pytest.mark.asyncio
async def test_send_procedure_card_blocked_bot_returns_false(monkeypatch):
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock(side_effect=Exception("bot blocked"))
    monkeypatch.setattr(notif, "get_bot", lambda: fake_bot)
    ok = await notif.send_procedure_card(111, "כותרת")
    assert ok is False


@pytest.mark.asyncio
async def test_send_procedure_card_bot_none_returns_false(monkeypatch):
    monkeypatch.setattr(notif, "get_bot", lambda: None)
    ok = await notif.send_procedure_card(111, "כותרת")
    assert ok is False


# ── RealProcedurePublisher broadcast ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_publisher_broadcasts_card_to_all_with_counts(monkeypatch):
    """N recipients → N card sends; counts preserved; a failing recipient is
    counted as skipped. [EDGE I4]"""
    sent_calls = []

    async def fake_card(tg_id, title, reply_markup=None):
        if tg_id == "blocked":
            return False
        sent_calls.append((tg_id, title))
        return True

    monkeypatch.setattr(notif, "send_procedure_card", fake_card)
    publisher = RealProcedurePublisher(keyboard_factory=lambda pid: start_quiz_kb(pid))
    summary = await publisher.broadcast(["111", "222", "blocked"], "נהל", "pid")
    assert summary == {"sent": 2, "skipped": 1, "total": 3}
    assert [c[0] for c in sent_calls] == ["111", "222"]


# ── on_view sends the card (no chunk loop) ───────────────────────────────────


def _stub_session():
    """A fake _session() — an async factory returning a session-like object whose
    ``close()`` is awaitable (repos + user resolver are stubbed separately)."""

    async def _sess():
        session = MagicMock()
        session.close = AsyncMock()
        return session

    return _sess


@pytest.mark.asyncio
async def test_on_view_sends_card_with_passed_keyboard(monkeypatch):
    """on_view sends ONE card (not a chunk loop); passed → '✅ עברת — מבחן חוזר'."""
    from app.bot.handlers import procedures as handler

    captured = {}

    async def fake_card(tg_id, title, reply_markup=None):
        captured["title"] = title
        captured["rows"] = reply_markup.inline_keyboard
        return True

    monkeypatch.setattr(handler, "send_procedure_card", fake_card)
    monkeypatch.setattr(handler, "_session", _stub_session())

    # A long procedure body that WOULD have chunked before — proves the card
    # path sends a single message regardless of body length.
    import uuid as _uuid

    pid = _uuid.uuid4()
    proc = MagicMock()
    proc.id = pid
    proc.title = "נהל כניסה"
    proc.body_text = "תוכן ארוך " * 200

    fake_repo = MagicMock()
    fake_repo.get_by_id = AsyncMock(return_value=proc)
    fake_attempt_repo = MagicMock()
    fake_attempt_repo.has_passed = AsyncMock(return_value=True)

    # on_view imports these lazily at call time, so patch the SOURCE modules.
    import app.procedures.repositories.procedure_repository as proc_repo_mod
    import app.procedures.repositories.attempt_repository as attempt_repo_mod

    monkeypatch.setattr(proc_repo_mod, "ProcedureRepository", lambda s: fake_repo)
    monkeypatch.setattr(attempt_repo_mod, "QuizAttemptRepository", lambda s: fake_attempt_repo)
    # _resolve_user is module-level in the handler.
    monkeypatch.setattr(handler, "_resolve_user", AsyncMock(return_value=MagicMock(id="u")))

    cb = MagicMock()
    cb.data = f"{kb.PROC_VIEW_PREFIX}{pid}"
    cb.from_user.id = 111
    cb.answer = AsyncMock()

    await handler.on_view(cb)
    assert cb.answer.await_count == 1
    assert captured["title"] == "נהל כניסה"
    # passed → the retake-style label on the quiz row
    assert captured["rows"][1][0].text == "✅ עברת — מבחן חוזר"
    # read row present (first)
    assert captured["rows"][0][0].text == "📖 קרא נוהל"


# ── Reminder send includes the keyboard ──────────────────────────────────────


@pytest.mark.asyncio
async def test_reminder_send_uses_reminder_text_with_keyboard(monkeypatch):
    """The reminder sends its reminder-specific framing (⏰ תזכורת — NOT the
    generic publish card) via send_notification, with the read+quiz keyboard.
    The title is HTML-escaped. Exercises the real ``_send`` closure inside
    ``run_procedure_reminders`` via a fake reminder service."""
    from app import scheduler
    from app.bot import notifications
    import app.database as dbmod
    import app.procedures.dependencies as depmod

    captured = {}

    async def fake_send_notification(telegram_id, text, reply_markup=None):
        captured["telegram_id"] = telegram_id
        captured["text"] = text
        captured["markup"] = reply_markup
        return True

    monkeypatch.setattr(notifications, "send_notification", fake_send_notification)

    class _FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(dbmod, "get_session", lambda: _FakeSession())

    def fake_build(session, send):
        # Capture the real _send closure; the fake service invokes it once.
        captured["send"] = send

        class _Svc:
            async def run(self, now):
                ok = await send("111", "proc-uuid", "נהל חירום <x>")
                return 1 if ok else 0

        return _Svc()

    monkeypatch.setattr(depmod, "build_reminder_service", fake_build)

    await scheduler.run_procedure_reminders()

    # The reminder text (not the publish card) was sent via send_notification.
    assert captured["text"].startswith("⏰ <b>תזכורת מבחן נוהל</b>")
    assert "טרם השלמת את המבחן" in captured["text"]
    assert "נא להשלים את המבחן בהקדם." in captured["text"]
    # The title is HTML-escaped (a literal '<' would otherwise break the send).
    assert "<b>נהל חירום &lt;x&gt;</b>" in captured["text"]
    assert "<x>" not in captured["text"]
    # The keyboard carries the read (web_app) + start-quiz buttons.
    rows = captured["markup"].inline_keyboard
    assert rows[0][0].text == "📖 קרא נוהל"
    assert rows[1][0].callback_data == f"{kb.QUIZ_START_PREFIX}proc-uuid"


# ── Deleted chunking machinery leaves no references ──────────────────────────


def test_no_references_to_deleted_chunk_helpers():
    """Grep-level guard: the deleted chunk helpers are gone from notifications."""
    assert not hasattr(notif, "send_procedure")
    assert not hasattr(notif, "chunk_message")
    assert not hasattr(notif, "_pack_procedure_chunks")
    assert not hasattr(notif, "_wrap_procedure_chunk")
    assert not hasattr(notif, "_hard_split_paragraph")
    assert not hasattr(notif, "_convert_paragraph_markers")
    assert not hasattr(notif, "_BOLD_PAIR")
    assert not hasattr(notif, "TG_MESSAGE_LIMIT")
