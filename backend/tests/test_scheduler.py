"""Tests for the weekly-rollover scheduler wiring (timing only).

The rollover *logic* is covered by test_auto_advance.py; here we only verify the
job is scheduled for Motzaei Shabbat (Sun 00:00 Asia/Jerusalem), respects the
enable flag, and delegates to WeekService.auto_advance_weeks.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app import scheduler as sched_mod


def test_start_scheduler_configures_sunday_midnight():
    s = sched_mod.start_scheduler()
    assert s is not None
    try:
        job = s.get_job(sched_mod._ROLLOVER_JOB_ID)
        assert job is not None
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert fields["day_of_week"] == "sun"
        assert fields["hour"] == "0"
        assert fields["minute"] == "0"
        assert str(job.trigger.timezone) == "Asia/Jerusalem"
    finally:
        s.shutdown(wait=False)


def test_start_scheduler_disabled(monkeypatch):
    stub = MagicMock(AUTO_ROLLOVER_ENABLED=False, SCHEDULER_TIMEZONE="Asia/Jerusalem")
    monkeypatch.setattr(sched_mod, "get_settings", lambda: stub)
    assert sched_mod.start_scheduler() is None


@pytest.mark.asyncio
async def test_run_weekly_rollover_calls_auto_advance(monkeypatch):
    import app.database as db_mod
    import app.services.week_service as ws_mod

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *a):
            return False

    service = MagicMock()
    service.auto_advance_weeks = AsyncMock()
    monkeypatch.setattr(db_mod, "get_session", lambda: FakeSession())
    monkeypatch.setattr(ws_mod, "WeekService", lambda *a, **k: service)

    await sched_mod.run_weekly_rollover()

    service.auto_advance_weeks.assert_awaited_once()
