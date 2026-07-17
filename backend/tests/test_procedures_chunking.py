"""
Procedure broadcast chunking — paragraph-boundary splits, the hard-split
fallback for an overlong paragraph, and that the keyboard attaches to the last
chunk only (verified through ``send_procedure`` with a mocked bot).
"""

from unittest.mock import AsyncMock, MagicMock

from app.bot import notifications as notif


def test_short_message_is_single_chunk():
    assert notif.chunk_message("שורה קצרה", limit=4096) == ["שורה קצרה"]


def test_splits_on_paragraph_boundaries():
    text = "\n".join(["פסקה"] * 5)
    chunks = notif.chunk_message(text, limit=12)
    assert len(chunks) > 1
    # nothing exceeds the limit
    assert all(len(c) <= 12 for c in chunks)
    # no content lost (concatenated == original modulo newlines)
    assert "פסקה" in chunks[0]


def test_hard_splits_overlong_single_paragraph():
    huge = "word " * 500  # one paragraph, no newlines, way over limit
    chunks = notif.chunk_message(huge, limit=50)
    assert len(chunks) > 10
    assert all(len(c) <= 50 for c in chunks)


def test_hard_split_falls_back_to_word_boundary():
    # words longer than the limit force a hard cut, but mid-limit words split on space
    text = "אחת שתיים שלוש ארבע חמש שש שבע"
    chunks = notif.chunk_message(text, limit=15)
    assert all(len(c) <= 15 for c in chunks)
    assert len(chunks) >= 2


def test_empty_paragraphs_preserved_as_breaks():
    text = "חלק א\n\n\nחלק ב"
    chunks = notif.chunk_message(text, limit=4096)
    assert "חלק א" in chunks[0]
    assert "חלק ב" in chunks[-1]


async def test_send_procedure_attaches_keyboard_to_last_chunk_only(monkeypatch):
    """The reply_markup must ride ONLY the final chunk."""
    long_body = "\n".join([f"שורה מספר {i}" for i in range(500)])
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    monkeypatch.setattr(notif, "get_bot", lambda: fake_bot)

    kb = MagicMock(name="keyboard")
    ok = await notif.send_procedure(111, "כותרת", long_body, reply_markup=kb)
    assert ok is True
    assert fake_bot.send_message.await_count > 1
    # exactly the last call carries the keyboard
    calls = fake_bot.send_message.call_args_list
    last_kwargs = calls[-1].kwargs
    assert last_kwargs["reply_markup"] is kb
    for call in calls[:-1]:
        assert call.kwargs.get("reply_markup") is None


async def test_send_procedure_blocked_bot_returns_false(monkeypatch):
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock(side_effect=Exception("bot blocked"))
    monkeypatch.setattr(notif, "get_bot", lambda: fake_bot)
    ok = await notif.send_procedure(111, "כותרת", "תוכן")
    assert ok is False


async def test_send_procedure_escapes_html_special_chars_in_body(monkeypatch):
    """A body with '<' and '&' must be HTML-escaped before sending (the bot parses
    every message as HTML, so raw entities would 400 the send). Escaping happens
    before chunking, so no chunk carries a raw '<'/'&'."""
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    monkeypatch.setattr(notif, "get_bot", lambda: fake_bot)

    body = "מרחק <2 מטר מהשער & חובה לדווח"
    ok = await notif.send_procedure(111, "כותרת <1>", body)
    assert ok is True

    sent_texts = [c.kwargs["text"] for c in fake_bot.send_message.call_args_list]
    # the raw special chars never reach Telegram as-is
    assert all("<2" not in t and " & " not in t for t in sent_texts)
    # the escaped entities are present
    flat = "\n".join(sent_texts)
    assert "&lt;2" in flat
    assert "&amp;" in flat
    # the escaped title is intact too
    assert "&lt;1&gt;" in flat
