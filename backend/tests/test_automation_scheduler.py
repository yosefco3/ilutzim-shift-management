"""Tests for the auto-open/auto-lock scheduler wiring (prompt 07).

Verifies sync_automation_jobs builds cron jobs from the DB settings (right
day/hour/minute, correct timezone), removes disabled jobs, reschedules on
change, and that the job callables delegate to the WeekService methods.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import scheduler as sched_mod


class _FakeSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *a):
        return False


def _patch_settings(monkeypatch, auto_open, auto_lock):
    import app.database as db_mod
    from app.services.settings_service import SettingsService

    monkeypatch.setattr(db_mod, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(
        SettingsService, "get_auto_open", AsyncMock(return_value=auto_open)
    )
    monkeypatch.setattr(
        SettingsService, "get_auto_lock", AsyncMock(return_value=auto_lock)
    )


@pytest_asyncio.fixture
async def sch():
    """A started scheduler (needed so replace_existing replaces in the jobstore)."""
    s = AsyncIOScheduler(timezone="Asia/Jerusalem")
    s.start(paused=True)  # started → jobs live in the jobstore, but nothing fires
    try:
        yield s
    finally:
        s.shutdown(wait=False)


def _fields(job):
    return {f.name: str(f) for f in job.trigger.fields}


# ── sync_automation_jobs ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_registers_enabled_jobs(monkeypatch, sch):
    _patch_settings(
        monkeypatch,
        {"enabled": True, "weekday": "sun", "hour": 7, "minute": 0},
        {"enabled": True, "weekday": "wed", "hour": 12, "minute": 30},
    )
    await sched_mod.sync_automation_jobs(sch)

    open_job = sch.get_job(sched_mod._AUTO_OPEN_JOB_ID)
    lock_job = sch.get_job(sched_mod._AUTO_LOCK_JOB_ID)
    assert open_job is not None and lock_job is not None

    of = _fields(open_job)
    assert of["day_of_week"] == "sun" and of["hour"] == "7" and of["minute"] == "0"
    lf = _fields(lock_job)
    assert lf["day_of_week"] == "wed" and lf["hour"] == "12" and lf["minute"] == "30"
    assert str(open_job.trigger.timezone) == "Asia/Jerusalem"


@pytest.mark.asyncio
async def test_sync_omits_disabled_job(monkeypatch, sch):
    _patch_settings(
        monkeypatch,
        {"enabled": True, "weekday": "sun", "hour": 7, "minute": 0},
        {"enabled": False, "weekday": "wed", "hour": 12, "minute": 0},
    )
    await sched_mod.sync_automation_jobs(sch)

    assert sch.get_job(sched_mod._AUTO_OPEN_JOB_ID) is not None
    assert sch.get_job(sched_mod._AUTO_LOCK_JOB_ID) is None


@pytest.mark.asyncio
async def test_sync_reschedules_and_removes_on_change(monkeypatch, sch):
    # First: open enabled at sun 07:00
    _patch_settings(
        monkeypatch,
        {"enabled": True, "weekday": "sun", "hour": 7, "minute": 0},
        {"enabled": False, "weekday": "wed", "hour": 12, "minute": 0},
    )
    await sched_mod.sync_automation_jobs(sch)
    assert _fields(sch.get_job(sched_mod._AUTO_OPEN_JOB_ID))["hour"] == "7"

    # Then admin moves it to 09:00 and disables it altogether on the next edit
    _patch_settings(
        monkeypatch,
        {"enabled": True, "weekday": "sun", "hour": 9, "minute": 0},
        {"enabled": False, "weekday": "wed", "hour": 12, "minute": 0},
    )
    await sched_mod.sync_automation_jobs(sch)
    assert _fields(sch.get_job(sched_mod._AUTO_OPEN_JOB_ID))["hour"] == "9"  # rescheduled, not duplicated

    _patch_settings(
        monkeypatch,
        {"enabled": False, "weekday": "sun", "hour": 9, "minute": 0},
        {"enabled": False, "weekday": "wed", "hour": 12, "minute": 0},
    )
    await sched_mod.sync_automation_jobs(sch)
    assert sch.get_job(sched_mod._AUTO_OPEN_JOB_ID) is None  # now removed


@pytest.mark.asyncio
async def test_sync_uses_passed_values_without_opening_session(monkeypatch, sch):
    """When the settings endpoint passes the freshly-written values in, the
    reschedule must use them and must NOT open its own session (which would read
    the previous, still-committed value and silently keep the OLD schedule)."""
    import app.database as db_mod

    def _boom():
        raise AssertionError("sync_automation_jobs opened a session despite passed values")

    monkeypatch.setattr(db_mod, "get_session", _boom)

    await sched_mod.sync_automation_jobs(
        sch,
        auto_open={"enabled": True, "weekday": "sat", "hour": 16, "minute": 0},
        auto_lock={"enabled": True, "weekday": "sat", "hour": 16, "minute": 30},
    )

    lf = _fields(sch.get_job(sched_mod._AUTO_LOCK_JOB_ID))
    assert lf["day_of_week"] == "sat" and lf["hour"] == "16" and lf["minute"] == "30"


@pytest.mark.asyncio
async def test_sync_noop_without_scheduler(monkeypatch):
    monkeypatch.setattr(sched_mod, "_scheduler", None)
    # Should not raise even though no scheduler is available.
    await sched_mod.sync_automation_jobs(None)


# ── job callables delegate to the service ─────────────────────────────────────

@pytest.mark.asyncio
async def test_run_auto_open_calls_service(monkeypatch):
    import app.database as db_mod
    import app.services.week_service as ws_mod

    service = MagicMock()
    service.auto_open_relevant_week = AsyncMock()
    monkeypatch.setattr(db_mod, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(ws_mod, "WeekService", lambda *a, **k: service)

    await sched_mod.run_auto_open()
    service.auto_open_relevant_week.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_auto_lock_calls_service(monkeypatch):
    import app.database as db_mod
    import app.services.week_service as ws_mod

    service = MagicMock()
    service.auto_lock_open_week = AsyncMock()
    monkeypatch.setattr(db_mod, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(ws_mod, "WeekService", lambda *a, **k: service)

    await sched_mod.run_auto_lock()
    service.auto_lock_open_week.assert_awaited_once()
