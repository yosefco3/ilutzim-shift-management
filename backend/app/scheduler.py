"""Background scheduler — the automatic Saturday-night (Motzaei Shabbat) rollover.

Every Sunday at 00:00 (Israel time) the active submission week is auto-locked and
the upcoming week is ensured, regardless of admin action. The actual logic lives
in ``WeekService.auto_advance_weeks`` and is idempotent/self-healing, so this
module only owns the *timing*: a weekly cron trigger plus a one-shot catch-up on
startup (covering a server that was down at midnight).
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings

logger = logging.getLogger("ilutzim")

_ROLLOVER_JOB_ID = "weekly_week_rollover"
_AUTO_OPEN_JOB_ID = "auto_open_week"
_AUTO_LOCK_JOB_ID = "auto_lock_week"

# Process-wide handle to the running scheduler, so the settings endpoint can
# reschedule the automation jobs after the admin edits them (no restart needed).
_scheduler: "AsyncIOScheduler | None" = None


def get_scheduler() -> "AsyncIOScheduler | None":
    """Return the running scheduler instance (None if not started)."""
    return _scheduler


async def run_weekly_rollover() -> None:
    """Lock the expired open week and ensure the upcoming one.

    Uses its own committed session (``get_session``) since it runs outside the
    FastAPI request lifecycle. Failures are logged and swallowed — the next run
    (or any admin weeks-list load) self-heals because the logic is idempotent.
    """
    try:
        from app.database import get_session
        from app.repositories.schedule_week_repository import ScheduleWeekRepository
        from app.repositories.user_repository import UserRepository
        from app.schedule_builder.dependencies import build_actual_schedule_service
        from app.services.week_service import WeekService

        async with get_session() as session:
            week_repo = ScheduleWeekRepository(session)
            user_repo = UserRepository(session)
            service = WeekService(
                week_repo, user_repo,
                actual_schedule_service=build_actual_schedule_service(session),
            )
            await service.auto_advance_weeks()
        logger.info("Weekly rollover completed")
    except Exception as exc:
        logger.warning("Weekly rollover failed: %s", exc)


async def run_auto_open() -> None:
    """Cron job: open the upcoming closed week (broadcasts to guards).

    Own committed session; idempotency + the silent/broadcast distinction live
    in ``WeekService``. Failures are logged and swallowed.
    """
    try:
        from app.database import get_session
        from app.repositories.schedule_week_repository import ScheduleWeekRepository
        from app.repositories.user_repository import UserRepository
        from app.services.week_service import WeekService

        async with get_session() as session:
            service = WeekService(
                ScheduleWeekRepository(session), UserRepository(session)
            )
            await service.auto_open_relevant_week()
        logger.info("Auto-open job completed")
    except Exception as exc:
        logger.warning("Auto-open job failed: %s", exc)


async def run_auto_lock() -> None:
    """Cron job: silently close the currently open week's submission window
    (OPEN → CLOSED, reopenable). Own committed session. (Job id kept as
    ``auto_lock_week`` for settings-key stability.)"""
    try:
        from app.database import get_session
        from app.repositories.schedule_week_repository import ScheduleWeekRepository
        from app.repositories.user_repository import UserRepository
        from app.services.week_service import WeekService

        async with get_session() as session:
            service = WeekService(
                ScheduleWeekRepository(session), UserRepository(session)
            )
            await service.auto_lock_open_week()
        logger.info("Auto-lock job completed")
    except Exception as exc:
        logger.warning("Auto-lock job failed: %s", exc)


async def run_attendance_alerts() -> None:
    """Interval job (stage 3): the three admin alerts — no-show, long shift,
    short rest. Own committed session; idempotent via the sent-ledger; the
    enabled/chat-id gate lives in the service. Failures logged and swallowed."""
    try:
        from app.attendance.dependencies import build_comparison_service
        from app.attendance.repositories.shift_repository import (
            AttendanceShiftRepository,
        )
        from app.attendance.services.alert_service import AlertService
        from app.bot.notifications import send_notification
        from app.database import get_session
        from app.utils.date_utils import now_il

        async with get_session() as session:
            comparison = await build_comparison_service(session)
            service = AlertService(
                comparison=comparison,
                shifts=AttendanceShiftRepository(session),
                config=comparison.config,
                session=session,
                send=send_notification,
            )
            sent = await service.run_checks(now=now_il().replace(tzinfo=None))
        if sent:
            logger.info("Attendance alerts dispatched: %d", sent)
    except Exception as exc:
        logger.warning("Attendance alerts job failed: %s", exc)


async def run_attendance_daily_sweep() -> None:
    """Cron job (stage 3): rebuild the recent attendance pairing window and
    flip stale open shifts to missing_out. Own committed session; idempotent;
    failures are logged and swallowed."""
    try:
        from app.attendance.repositories.event_repository import (
            AttendanceEventRepository,
        )
        from app.attendance.repositories.shift_repository import (
            AttendanceShiftRepository,
        )
        from app.attendance.services.pairing_service import PairingService
        from app.database import get_session
        from app.utils.date_utils import now_il

        async with get_session() as session:
            service = PairingService(
                AttendanceEventRepository(session),
                AttendanceShiftRepository(session),
            )
            await service.daily_sweep(now=now_il().replace(tzinfo=None))
        logger.info("Attendance daily sweep completed")
    except Exception as exc:
        logger.warning("Attendance daily sweep failed: %s", exc)


async def run_procedure_reminders() -> None:
    """Daily cron job (procedures / סד"פ): remind guards who haven't passed a
    published procedure (older than 48h) — one reminder per guard per procedure.
    Own committed session; idempotent via the ``ProcedureReminderSent`` ledger;
    failures are logged and swallowed. Only runs when PROCEDURES_ENABLED."""
    try:
        from app.database import get_session
        from app.procedures.dependencies import build_reminder_service
        from app.utils.date_utils import now_il

        async def _send(telegram_id, procedure_id, title):
            import html as _html

            from app.bot.keyboards.procedures import start_quiz_kb
            from app.bot.notifications import send_notification

            # Reminder-specific framing (NOT the generic publish card) — a guard
            # must be able to tell this is a nudge about an UNFINISHED quiz. The
            # keyboard carries the read (web_app) + start-quiz buttons (the "card
            # + keyboard" intent for reminders). Title is HTML-escaped: the bot
            # parses the message as HTML, so a literal '<'/'&' in the title would
            # break the send (the original left it unescaped).
            text = (
                "⏰ <b>תזכורת מבחן נוהל</b>\n\n"
                f"טרם השלמת את המבחן על הנוהל:\n<b>{_html.escape(title)}</b>\n\n"
                "נא להשלים את המבחן בהקדם."
            )
            return await send_notification(
                telegram_id, text, reply_markup=start_quiz_kb(str(procedure_id))
            )

        async with get_session() as session:
            service = build_reminder_service(session, send=_send)
            await service.run(now=now_il().replace(tzinfo=None))
    except Exception as exc:
        logger.warning("Procedure reminders job failed: %s", exc)


def _apply_automation_job(scheduler, job_id, cfg, func, timezone) -> None:
    """Add/replace the job when enabled, or remove it when disabled."""
    if cfg.get("enabled"):
        scheduler.add_job(
            func,
            trigger="cron",
            day_of_week=cfg["weekday"],
            hour=cfg["hour"],
            minute=cfg["minute"],
            timezone=timezone,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )
        logger.info(
            "Scheduled %s: %s %02d:%02d %s",
            job_id, cfg["weekday"], cfg["hour"], cfg["minute"], timezone,
        )
    elif scheduler.get_job(job_id) is not None:
        scheduler.remove_job(job_id)
        logger.info("Removed disabled automation job: %s", job_id)
    else:
        # enabled=False and no job registered. Log it explicitly so a missing
        # auto-open/auto-lock is visible in the logs (silence here previously
        # made a disabled job indistinguishable from a scheduling failure).
        logger.info("Automation job %s is disabled (enabled=False) — not scheduled", job_id)


async def sync_automation_jobs(scheduler=None, *, auto_open=None, auto_lock=None) -> None:
    """(Re)build the auto-open/auto-lock cron jobs from the settings.

    Registers fixed-id jobs (``replace_existing=True`` so an edit never
    duplicates them); a disabled block removes its job. Called on startup and
    after a settings update so a change takes effect immediately, without a
    restart. No-op if the scheduler is not running (e.g. AUTO_ROLLOVER_ENABLED=false).

    ``auto_open``/``auto_lock`` may be passed in by the settings endpoint so the
    reschedule uses the values from the *same* (already-written) request session.
    Spinning up a fresh session here instead would read the previous COMMITTED
    state — the admin's write is only flushed, not yet committed, until request
    teardown — and reschedule to the OLD time (a silent no-op). When omitted
    (startup path) the values are read from the DB with this function's own session.
    """
    scheduler = scheduler or _scheduler
    if scheduler is None:
        return

    try:
        if auto_open is None or auto_lock is None:
            from app.database import get_session
            from app.repositories.system_settings_repository import SystemSettingsRepository
            from app.services.settings_service import SettingsService

            async with get_session() as session:
                settings_service = SettingsService(SystemSettingsRepository(session))
                if auto_open is None:
                    auto_open = await settings_service.get_auto_open()
                if auto_lock is None:
                    auto_lock = await settings_service.get_auto_lock()

        timezone = get_settings().SCHEDULER_TIMEZONE
        _apply_automation_job(scheduler, _AUTO_OPEN_JOB_ID, auto_open, run_auto_open, timezone)
        _apply_automation_job(scheduler, _AUTO_LOCK_JOB_ID, auto_lock, run_auto_lock, timezone)
    except Exception as exc:
        logger.warning("Failed to sync automation jobs: %s", exc)


def start_scheduler() -> AsyncIOScheduler | None:
    """Start the weekly rollover scheduler. Returns the scheduler, or None if
    disabled. Must be called inside a running event loop (FastAPI lifespan)."""
    settings = get_settings()
    if not settings.AUTO_ROLLOVER_ENABLED:
        logger.info("Auto rollover disabled (AUTO_ROLLOVER_ENABLED=false)")
        return None

    scheduler = AsyncIOScheduler(timezone=settings.SCHEDULER_TIMEZONE)
    # Motzaei Shabbat 00:00 == Sunday 00:00 Israel time.
    scheduler.add_job(
        run_weekly_rollover,
        trigger="cron",
        day_of_week="sun",
        hour=0,
        minute=0,
        id=_ROLLOVER_JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    # Stage 3 — attendance pairing sweep, daily 04:30 IL (quiet hour, after any
    # night shift's 16h ceiling logic has data to work with). Flag-gated.
    if settings.ATTENDANCE_ENABLED:
        scheduler.add_job(
            run_attendance_daily_sweep,
            trigger="cron",
            hour=4,
            minute=30,
            id="attendance_daily_sweep",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )
        # Admin alerts — every 10 minutes; the on/off toggle and chat id are
        # read from the DB settings on each run (no restart needed).
        scheduler.add_job(
            run_attendance_alerts,
            trigger="interval",
            minutes=10,
            id="attendance_alerts",
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True,
        )

    # Procedure-quiz (סד"פ) — daily reminder for guards who haven't passed a
    # published procedure. Fixed hour (12:00 Israel), flag-gated, idempotent.
    if settings.PROCEDURES_ENABLED:
        scheduler.add_job(
            run_procedure_reminders,
            trigger="cron",
            hour=12,
            minute=0,
            id="procedure_reminders",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )

    scheduler.start()
    logger.info(
        "Weekly rollover scheduled: Sun 00:00 %s", settings.SCHEDULER_TIMEZONE
    )

    global _scheduler
    _scheduler = scheduler
    return scheduler
