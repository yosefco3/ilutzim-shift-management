"""
Tests for the personal-schedule Telegram message (part B, task 10·04).

Two building blocks, tested in isolation (the wiring to "publish" is task 05):
- ``format_personal_schedule`` — pure formatter (guard read-model → Hebrew text).
- ``send_personal_schedules`` — per-guard broadcast over a faked bot.
"""

import uuid
from datetime import date

import pytest

from app.bot.notifications import format_personal_schedule
from app.schedule_builder.services.schedule_export_service import (
    GuardSchedule,
    GuardShift,
    ScheduleExportService,
    WeekSchedule,
)

WEEK_START = date(2025, 7, 12)  # a Saturday-anchored ISO week is irrelevant here;
WEEK_END = date(2025, 7, 18)    # the formatter just uses day_index offsets.


def _guard(name, shifts, telegram_id=None, phone=""):
    """``shifts`` are (day, name, start, end) or (day, name, start, end, is_event)."""
    return GuardSchedule(
        user_id=uuid.uuid4(), user_name=name, telegram_id=telegram_id,
        phone_number=phone,
        shifts=[
            GuardShift(
                day_index=t[0], date="", position_id=uuid.uuid4(),
                position_name=t[1], start=t[2], end=t[3],
                is_event=t[4] if len(t) > 4 else False,
            )
            for t in shifts
        ],
    )


# ── formatter ─────────────────────────────────────────────────────────


class TestFormatPersonalSchedule:
    def test_lists_days_positions_and_hours_in_order(self):
        guard = _guard("אבי כהן", [
            (0, "ארנונה", "07:00", "15:00"),
            (1, "קומה 6", "15:00", "23:00"),
        ])
        text = format_personal_schedule(guard, WEEK_START, WEEK_END)

        assert "🗓️ הסידור שלך לשבוע 12/07/2025 – 18/07/2025" in text
        assert "ראשון 12/07" in text
        assert "ארנונה · 07:00–15:00" in text
        assert "שני 13/07" in text
        assert "קומה 6 · 15:00–23:00" in text
        # Sunday block precedes Monday block.
        assert text.index("ראשון 12/07") < text.index("שני 13/07")

    def test_cross_midnight_tagged(self):
        guard = _guard("אבי כהן", [(4, "סייר 1", "23:00", "07:00")])
        text = format_personal_schedule(guard, WEEK_START, WEEK_END)
        assert "סייר 1 · 23:00–07:00 (עד למחרת)" in text

    def test_two_shifts_same_day_two_bullets(self):
        guard = _guard("אבי כהן", [
            (2, "ארנונה", "07:00", "15:00"),
            (2, "קומה 6", "15:00", "19:00"),
        ])
        text = format_personal_schedule(guard, WEEK_START, WEEK_END)
        # One day header, two bullets under it (day_index 2 → 14/07).
        assert text.count("שלישי 14/07") == 1
        assert "ארנונה · 07:00–15:00" in text
        assert "קומה 6 · 15:00–19:00" in text

    def test_no_shifts_message(self):
        guard = _guard("דנה לוי", [])
        text = format_personal_schedule(guard, WEEK_START, WEEK_END)
        assert text == (
            "לא שובצת השבוע (12/07–18/07). לשאלות פנה לאחראי היחידה."
        )

    def test_event_rendered_as_dedicated_sentence(self):
        guard = _guard("אבי כהן", [
            (0, "ארנונה", "07:00", "15:00"),
            (0, "רענון", "07:00", "15:00", True),
        ])
        text = format_personal_schedule(guard, WEEK_START, WEEK_END)
        # The normal shift is a bullet; the event is a 📣 sentence, not a bullet.
        assert "  • ארנונה · 07:00–15:00" in text
        assert "📣 יש לך רענון ביום ראשון 12/07" in text
        assert "   משעה 07:00 עד 15:00" in text
        assert "• רענון" not in text
        # The event block comes after the routine schedule.
        assert text.index("ארנונה") < text.index("רענון")

    def test_event_cross_midnight_tagged(self):
        guard = _guard("אבי כהן", [(4, "כוננות", "23:00", "07:00", True)])
        text = format_personal_schedule(guard, WEEK_START, WEEK_END)
        assert "📣 יש לך כוננות ביום חמישי 16/07" in text
        assert "   משעה 23:00 עד 07:00 (עד למחרת)" in text

    def test_only_events_still_shows_header_not_unscheduled(self):
        guard = _guard("דנה לוי", [(2, "ישיבת מועצה", "09:00", "12:00", True)])
        text = format_personal_schedule(guard, WEEK_START, WEEK_END)
        assert "🗓️ הסידור שלך לשבוע" in text
        assert "לא שובצת" not in text
        assert "📣 יש לך ישיבת מועצה ביום שלישי 14/07" in text


# ── broadcast ─────────────────────────────────────────────────────────


def _service_with_schedule(guards):
    """A ScheduleExportService whose get_week_schedule is stubbed to return the
    given guards (board/assignment/user deps are unused on this path)."""
    svc = ScheduleExportService(None, None, None)
    week = type("W", (), {
        "start_date": WEEK_START, "end_date": WEEK_END,
    })()
    ws = WeekSchedule(week=week, days=[], by_position=[], by_guard=guards)

    async def _fake_get(week_id):
        return ws

    svc.get_week_schedule = _fake_get
    return svc


class TestSendPersonalSchedules:
    async def test_counts_sent_skipped_and_survives_failure(self, monkeypatch):
        good = _guard("אבי כהן", [(0, "ארנונה", "07:00", "15:00")], telegram_id="111")
        no_tg = _guard("דנה לוי", [(0, "ארנונה", "07:00", "15:00")])  # no telegram_id
        failing = _guard("גדי מור", [(1, "קומה 6", "15:00", "23:00")], telegram_id="999")

        sent_to = []

        async def fake_send(telegram_id, text, reply_markup=None):
            if telegram_id == "999":
                raise RuntimeError("telegram down")
            sent_to.append(telegram_id)
            return True

        # Patch the underlying sender used by notify_personal_schedule.
        monkeypatch.setattr(
            "app.bot.notifications.send_notification", fake_send
        )

        svc = _service_with_schedule([good, no_tg, failing])
        result = await svc.send_personal_schedules(uuid.uuid4())

        # no_tg is skipped (no telegram_id); the 999 guard HAD a telegram_id but
        # its delivery raised → counted as failed, not skipped.
        assert result == {"sent": 1, "skipped": 1, "failed": 1, "total": 3}
        assert sent_to == ["111"]  # only the deliverable, non-failing guard

    async def test_all_delivered(self, monkeypatch):
        g1 = _guard("א", [(0, "ארנונה", "07:00", "15:00")], telegram_id="1")
        g2 = _guard("ב", [], telegram_id="2")  # scheduled-empty still gets a message

        async def fake_send(telegram_id, text, reply_markup=None):
            return True

        monkeypatch.setattr(
            "app.bot.notifications.send_notification", fake_send
        )

        svc = _service_with_schedule([g1, g2])
        result = await svc.send_personal_schedules(uuid.uuid4())
        assert result == {"sent": 2, "skipped": 0, "failed": 0, "total": 2}

    async def test_schedule_png_attached_only_to_delivered_guards(self, monkeypatch):
        good = _guard("א", [(0, "ארנונה", "07:00", "15:00")], telegram_id="1")
        no_tg = _guard("ב", [(0, "ארנונה", "07:00", "15:00")])  # skipped, no telegram
        failing = _guard("ג", [(1, "קומה 6", "15:00", "23:00")], telegram_id="9")

        async def fake_send(telegram_id, text, reply_markup=None):
            return telegram_id != "9"  # guard "9" fails to receive its message

        photos_to = []

        async def fake_photo(telegram_id, image_bytes, filename, caption=None):
            photos_to.append((telegram_id, image_bytes, filename))
            return True

        monkeypatch.setattr("app.bot.notifications.send_notification", fake_send)
        monkeypatch.setattr("app.bot.notifications.send_photo", fake_photo)

        svc = _service_with_schedule([good, no_tg, failing])
        result = await svc.send_personal_schedules(
            uuid.uuid4(), schedule_png=b"PNGBYTES"
        )

        assert result == {"sent": 1, "skipped": 1, "failed": 1, "total": 3}
        # The image goes only to the guard whose personal message was delivered.
        assert [d[0] for d in photos_to] == ["1"]
        assert photos_to[0][1] == b"PNGBYTES"
        assert photos_to[0][2].endswith(".png")

    async def test_no_png_sent_when_not_provided(self, monkeypatch):
        g1 = _guard("א", [(0, "ארנונה", "07:00", "15:00")], telegram_id="1")

        async def fake_send(telegram_id, text, reply_markup=None):
            return True

        async def boom_photo(*a, **k):  # pragma: no cover - must not run
            raise AssertionError("no image should be sent when schedule_png is None")

        monkeypatch.setattr("app.bot.notifications.send_notification", fake_send)
        monkeypatch.setattr("app.bot.notifications.send_photo", boom_photo)

        svc = _service_with_schedule([g1])
        result = await svc.send_personal_schedules(uuid.uuid4())
        assert result == {"sent": 1, "skipped": 0, "failed": 0, "total": 1}


# ── preview (dry run) ─────────────────────────────────────────────────


class TestPreviewPersonalSchedules:
    async def test_returns_messages_without_sending(self, monkeypatch):
        # A sender that would explode if called — the preview must never send.
        async def boom(*a, **k):  # pragma: no cover - must not run
            raise AssertionError("preview must not send")

        monkeypatch.setattr("app.bot.notifications.send_notification", boom)

        good = _guard(
            "אבי כהן", [(0, "ארנונה", "07:00", "15:00")],
            telegram_id="111", phone="0500000111",
        )
        no_tg = _guard("דנה לוי", [(0, "ארנונה", "07:00", "15:00")], phone="0500000222")

        svc = _service_with_schedule([good, no_tg])
        items = await svc.preview_personal_schedules(uuid.uuid4())

        # Guards with no linked Telegram are floated to the top so the admin
        # notices them (their schedule can't be delivered over the bot).
        assert [i["user_name"] for i in items] == ["דנה לוי", "אבי כהן"]
        # would_send mirrors "has a telegram_id" — exactly who the broadcast sends to.
        assert [i["would_send"] for i in items] == [False, True]
        assert items[1]["telegram_id"] == "111"
        assert items[1]["phone_number"] == "0500000111"
        assert items[0]["telegram_id"] is None
        # The message is byte-identical to what the broadcast would format.
        assert items[1]["message"] == format_personal_schedule(good, WEEK_START, WEEK_END)
        assert "ארנונה · 07:00–15:00" in items[1]["message"]
