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


# ── Bold markers → <b>, blockquote wrapping, chunk invariants ─────────────────


def _sent_texts(fake_bot):
    return [c.kwargs["text"] for c in fake_bot.send_message.call_args_list]


def _assert_chunks_balanced_and_within_limit(chunks):
    """Every chunk ≤4096 chars (incl. tags) with balanced <b> tags and no
    blockquote (the collapsed-quote experiment was reverted 2026-07-18)."""
    for chunk in chunks:
        assert len(chunk) <= 4096, f"chunk over limit ({len(chunk)} chars)"
        assert chunk.count("<b>") == chunk.count("</b>"), f"unbalanced <b>: {chunk!r}"
        assert "<blockquote" not in chunk, f"blockquote reintroduced: {chunk!r}"


async def test_send_procedure_converts_bold_markers_to_html(monkeypatch):
    """A *…* span becomes <b>…</b>; text inside AND outside it is escaped."""
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    monkeypatch.setattr(notif, "get_bot", lambda: fake_bot)

    body = "לפני *מודגש <בפנים>* וגם <בחוץ"
    await notif.send_procedure(1, "כותרת", body)

    sent = "\n".join(_sent_texts(fake_bot))
    # the bold span is wrapped; its '<'/'>' escaped
    assert "<b>מודגש &lt;בפנים&gt;</b>" in sent
    # the '<' outside the bold span is escaped too — never raw
    assert "&lt;בחוץ" in sent
    assert "<בפנים" not in sent
    assert "<בחוץ" not in sent


async def test_send_procedure_odd_asterisk_is_literal(monkeypatch):
    """A lone asterisk (no closing partner) stays literal — no <b> emitted."""
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    monkeypatch.setattr(notif, "get_bot", lambda: fake_bot)

    body = "מחיר 5* שקל"  # one asterisk → unpaired → literal
    await notif.send_procedure(1, "כותרת", body)

    sent = "\n".join(_sent_texts(fake_bot))
    # the lone asterisk survived, and the only <b> is the title's
    assert "5* שקל" in sent
    assert sent.count("<b>") == 1  # title only — body has no bold tag


async def test_send_procedure_plain_message_bold_title(monkeypatch):
    """Regular (non-collapsed) message: bold title line + plain body."""
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    monkeypatch.setattr(notif, "get_bot", lambda: fake_bot)

    await notif.send_procedure(1, "הנוהל", "תוכן הנוהל")

    chunks = _sent_texts(fake_bot)
    assert len(chunks) == 1
    assert chunks[0] == "📜 <b>הנוהל</b>\n\nתוכן הנוהל"


async def test_send_procedure_chunks_balanced_and_within_limit(monkeypatch):
    """A long body with bold markers fans out to chunks that stay ≤4096 chars
    with balanced tags (no <b>/<blockquote> ever split across a message)."""
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    monkeypatch.setattr(notif, "get_bot", lambda: fake_bot)

    para = "פסקה עם *מודגש* " + ("תוכן " * 200)
    body = "\n".join([para] * 60)  # forces several chunks
    await notif.send_procedure(1, "כותרת ארוכה", body)

    chunks = _sent_texts(fake_bot)
    assert len(chunks) > 1
    _assert_chunks_balanced_and_within_limit(chunks)
    # the bold marker survived into at least one chunk's body
    assert any("<b>מודגש</b>" in c for c in chunks)


async def test_send_procedure_overlong_paragraph_strips_bold_and_splits(monkeypatch):
    """A single paragraph too long for a chunk falls back to plain hard-split
    text: balanced, ≤limit, and its bold tags stripped (correctness over
    formatting for the pathological case)."""
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    monkeypatch.setattr(notif, "get_bot", lambda: fake_bot)

    body = "*מודגש* " + ("תוכן " * 1500)  # one paragraph, well over 4096
    await notif.send_procedure(1, "נוהל", body)

    chunks = _sent_texts(fake_bot)
    assert len(chunks) > 1
    _assert_chunks_balanced_and_within_limit(chunks)
    # the title is the only <b> — the overlong paragraph's bold was stripped
    assert sum(c.count("<b>") for c in chunks) == 1


async def test_send_procedure_keyboard_still_last_chunk_only(monkeypatch):
    """The reply_markup still rides the final chunk only (regression guard for
    the paragraph-packing)."""
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    monkeypatch.setattr(notif, "get_bot", lambda: fake_bot)

    long_body = "\n".join([f"שורה מספר {i}" for i in range(500)])
    kb = MagicMock(name="keyboard")
    await notif.send_procedure(111, "כותרת", long_body, reply_markup=kb)

    calls = fake_bot.send_message.call_args_list
    assert calls[-1].kwargs["reply_markup"] is kb
    for call in calls[:-1]:
        assert call.kwargs.get("reply_markup") is None
    _assert_chunks_balanced_and_within_limit(_sent_texts(fake_bot))


async def test_send_procedure_plain_text_unchanged(monkeypatch):
    """A stored procedure with no markers renders escaped, as a regular
    message — no blockquote, no stray <b> in the body."""
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    monkeypatch.setattr(notif, "get_bot", lambda: fake_bot)

    body = "סעיף אחד\n\nסעיף שני עם < וגם & בפנים"
    await notif.send_procedure(1, "נוהל", body)

    chunks = _sent_texts(fake_bot)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert "סעיף אחד\n\nסעיף שני עם &lt; וגם &amp; בפנים" in chunk
    assert "<blockquote" not in chunk
    assert chunk.count("<b>") == 1  # title only
