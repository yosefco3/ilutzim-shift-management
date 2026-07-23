"""
WeekService — business logic for schedule week management.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.constants import WeekStatus
from app.exceptions import InvalidTransitionException, WeekLockedException
from app.messages import Messages
from app.models.schedule_week import ScheduleWeek
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.schemas.week_schemas import DayItem, WeekCreate, WeekResponse, WeekWithDaysResponse
from app.utils.date_utils import (
    now_il,
    today_il,
    week_range,
)


logger = logging.getLogger("ilutzim")

# Allowed week-status transitions (3-state model).
#
#   CLOSED = submissions closed; admin may edit the board + constraints on behalf
#            of guards (override_lock), and "publish" broadcasts the schedule
#            WITHOUT changing status — the week stays CLOSED.
#   OPEN   = submissions accepted; stamps ``opened_at`` on first entry.
#   LOCKED = final, non-reopenable. Reached ONLY by the Sunday rollover
#            (``lock_expired_open_weeks``, silent) when ``start_date`` arrives;
#            it locks BOTH the board and constraint submission. No publish/manual
#            path produces LOCKED. The ``→ locked`` edge below exists for that
#            rollover call.
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "closed": ["open", "locked"],
    "open": ["closed", "locked"],
    "locked": [],  # terminal — final, non-reopenable
}

# APScheduler day_of_week tokens → Python ``date.weekday()`` index (Mon=0 … Sun=6).
# Used to compute the weekly auto-open/auto-lock moments for the catch-up open.
_PY_WEEKDAY: dict[str, int] = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}


class WeekService:
    """Orchestrates schedule week lifecycle."""

    def __init__(
        self, week_repo: ScheduleWeekRepository, user_repo=None,
        schedule_export_service=None, actual_schedule_service=None,
    ) -> None:
        self._week_repo = week_repo
        self._user_repo = user_repo
        # The schedule read model (part B) — powers the personal-schedule
        # broadcast on publish. Optional so non-publish paths construct with None.
        self._schedule_export = schedule_export_service
        # The actual-schedule seeder (part B) — the rollover births the week's
        # editable execution copy the moment it locks. Optional and best-effort:
        # paths constructed without it (bot) rely on the lazy seed on first read.
        self._actual_schedule = actual_schedule_service

    async def create_week(self, data: WeekCreate) -> WeekResponse:
        """Create a new schedule week."""
        logger.info(f"Creating week: {data.start_date} to {data.end_date}")
        week = ScheduleWeek(
            start_date=data.start_date,
            end_date=data.end_date,
            status=WeekStatus.CLOSED,
        )
        created = await self._week_repo.save(week)
        logger.info(f"Week created: id={created.id}")
        return WeekResponse.model_validate(created)

    async def get_all_weeks(self) -> list[WeekResponse]:
        """Return all schedule weeks, after the automatic weekly advance."""
        await self.auto_advance_weeks()
        weeks = await self._week_repo.get_all()
        return [WeekResponse.model_validate(w) for w in weeks]

    async def change_week_status(
        self, week_id: uuid.UUID, new_status: WeekStatus, notify: bool = True,
    ) -> WeekResponse:
        """Transition a week to a new status.

        Validates the transition against ALLOWED_TRANSITIONS (3-state model:
        closed ⇄ open, and either → locked; locked is terminal). Reaching LOCKED
        is the Sunday rollover's job only (``lock_expired_open_weeks``, silent) —
        no manual/publish path locks a week anymore.

        ``notify`` controls the Telegram broadcast. Manual admin transitions
        notify guards; the automatic Saturday-night rollover locks silently
        (``notify=False``) to avoid a midnight broadcast.
        """
        week = await self._get_week_or_raise(week_id)
        old_status = week.status

        # Reject same-status (no-op)
        if old_status == new_status:
            allowed = ", ".join(ALLOWED_TRANSITIONS.get(old_status, []))
            raise InvalidTransitionException(
                f"לא ניתן לשנות סטטוס מ-{old_status} ל-{new_status}."
                f" מעברים אפשריים: {allowed or 'אין'}"
            )

        # Validate transition is in the allowed list
        allowed_next = ALLOWED_TRANSITIONS.get(old_status, [])
        if new_status not in allowed_next:
            allowed_str = ", ".join(allowed_next) if allowed_next else "אין"
            raise InvalidTransitionException(
                f"לא ניתן לשנות סטטוס מ-{old_status} ל-{new_status}."
                f" מעברים אפשריים: {allowed_str}"
            )

        # No-reopen + single-open (B-1 · B-7). OPEN is a semantic (data-dependent)
        # rule on top of ALLOWED_TRANSITIONS: it is permitted ONLY for the upcoming
        # week that never ran its submission window — the same condition the
        # auto-open path uses (opened_at IS NULL, start_date in the future) — and
        # only when no other week is already OPEN. This removes the B-1 scenario
        # (opening an old week → a second OPEN week) at the root, which in turn
        # removes B-7 (auto-lock re-closing a hand-opened week) since such a week
        # can never be opened in the first place.
        if new_status == WeekStatus.OPEN:
            if week.opened_at is not None:
                raise ValueError(Messages.VAL_WEEK_ALREADY_RAN)
            if week.start_date <= today_il():
                raise ValueError(Messages.VAL_WEEK_NOT_UPCOMING)
            existing_open = await self._week_repo.get_current_open_week()
            if existing_open is not None and existing_open.id != week.id:
                raise ValueError(Messages.VAL_ANOTHER_WEEK_OPEN)

        # Stamp the first time a week is opened. ``opened_at`` is what tells the
        # auto-open cron a week was already opened, so it is never auto-reopened
        # after its submission window closes (which now returns it to CLOSED).
        # Re-opening a previously-opened week keeps the original timestamp.
        update_fields: dict = {"status": new_status}
        if new_status == WeekStatus.OPEN and week.opened_at is None:
            # naive UTC to match the naive ``timestamp`` column (asyncpg rejects
            # tz-aware values for ``timestamp without time zone``).
            update_fields["opened_at"] = datetime.now(timezone.utc).replace(tzinfo=None)

        updated = await self._week_repo.update(week.id, **update_fields)
        logger.info(f"Week {week_id}: {old_status} -> {new_status}")

        # Send Telegram notifications on status change (skipped for silent
        # automatic transitions, e.g. the Saturday-night auto-lock).
        if notify:
            try:
                from app.bot.notifications import notify_week_locked, notify_week_opened

                telegram_ids: list[int] = []
                if self._user_repo is not None:
                    users = await self._user_repo.get_all()
                    telegram_ids = [u.telegram_id for u in users if u.telegram_id]

                if telegram_ids:
                    if new_status == WeekStatus.OPEN:
                        await notify_week_opened(updated.start_date, updated.end_date, telegram_ids)
                    elif new_status == WeekStatus.LOCKED:
                        await notify_week_locked(updated.start_date, updated.end_date, telegram_ids)
            except Exception as exc:
                logger.warning(f"Failed to send status-change notification: {exc}")

        return WeekResponse.model_validate(updated)

    async def publish_week(self, week_id: uuid.UUID) -> dict:
        """Publish (or re-publish) a week: broadcast each guard their personal
        schedule + the schedule-grid PNG.

        This is a **pure broadcast**. It does NOT change the week's status and it
        does NOT create the next week. The week stays CLOSED — publishing never
        locks. The admin can keep editing the board and press publish again as
        long as the week has not started (``start_date > today``); ``published_at``
        is stamped each time so the UI can tell "publish" from "re-publish".
        Creating the next week is solely the Sunday rollover's job.

        Returns ``{"sent", "skipped", "failed", "total", "republished"}`` where
        ``republished`` is True when the week already carried a ``published_at``.

          - **CLOSED (upcoming, not started):** stamp ``published_at`` + broadcast.
          - **OPEN:** rejected — close submissions before publishing.
          - **LOCKED (rollover, final) or a week that already started:** rejected —
            nothing left to publish.
        """
        week = await self._get_week_or_raise(week_id)
        status = week.status

        if status == WeekStatus.OPEN:
            raise InvalidTransitionException(
                "יש לסגור את ההגשות לפני הפרסום"
            )
        if status == WeekStatus.LOCKED:
            raise InvalidTransitionException(
                "השבוע נעול סופית — לא ניתן לפרסם"
            )
        # CLOSED — only the upcoming, not-yet-started week is publishable.
        if not await self._is_publishable_week(week):
            raise InvalidTransitionException(
                "השבוע כבר התחיל — לא ניתן לפרסם"
            )

        republished = week.published_at is not None
        # Naive UTC to match the naive ``timestamp`` column (asyncpg rejects
        # tz-aware values), mirroring how ``opened_at`` is stamped.
        await self._week_repo.update(
            week_id, published_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )

        summary = {"sent": 0, "skipped": 0, "failed": 0, "total": 0}
        if self._schedule_export is not None:
            # Build the general schedule-grid PNG once so every guard receives it
            # alongside their personal message — a phone-friendly image, not an
            # .xlsx. Best-effort: if rendering fails, guards still get their
            # personal schedules (the image is extra).
            schedule_png = None
            try:
                from app.services.excel_export_service import ExcelExportService

                excel_service = ExcelExportService(
                    None, self._user_repo, self._week_repo, self._schedule_export
                )
                schedule_png = await excel_service.export_schedule_grid_png(week_id)
            except Exception as exc:
                logger.error(
                    "publish_week: schedule PNG generation failed for %s — %s",
                    week_id, exc,
                )
            try:
                summary = await self._schedule_export.send_personal_schedules(
                    week_id, schedule_png=schedule_png
                )
            except Exception as exc:
                logger.error(
                    "publish_week: personal-schedule broadcast failed for %s — %s",
                    week_id, exc,
                )
                # ``published_at`` is already stamped — don't report success
                # either: mark every guard as failed so the admin sees the
                # broadcast did not go through and can press publish again.
                total = summary.get("total", 0)
                summary = {"sent": 0, "skipped": 0, "failed": total, "total": total}
        # Surface partial failures the admin would otherwise miss (prod suppresses
        # INFO, so a per-guard failure could vanish).
        if summary.get("failed"):
            logger.warning(
                "publish_week %s: %d of %d personal schedules failed to send",
                week_id, summary["failed"], summary.get("total", 0),
            )
        return {**summary, "republished": republished}

    async def preview_publish(self, week_id: uuid.UUID) -> list[dict]:
        """Dry run of publish: return the personal-schedule message each guard
        *would* receive, without sending anything and without touching status.

        Works on any week that has a built schedule (no status gate) so the admin
        can inspect the messages before the irreversible publish/lock. Returns an
        empty list if the read model isn't wired.
        """
        if self._schedule_export is None:
            return []
        return await self._schedule_export.preview_personal_schedules(week_id)

    async def _is_publishable_week(self, week: ScheduleWeek) -> bool:
        """Whether ``week`` is the week the publish button belongs to — the
        nearest one that has NOT started yet (``start_date > today``), i.e. the
        upcoming week guards submitted for, finalized before it goes live. Falls
        back to the latest week only when no upcoming week exists. Once a week
        starts there is nothing left to publish, so it is no longer publishable.
        Matches the resolution the UI uses to place the publish/re-publish button.
        """
        target = await self._week_repo.get_upcoming_unstarted_week(today_il())
        if target is None:
            target = await self._week_repo.get_latest_week()
        return target is not None and target.id == week.id

    async def get_week(self, week_id: uuid.UUID) -> WeekResponse:
        """Return a single week by ID."""
        week = await self._get_week_or_raise(week_id)
        return WeekResponse.model_validate(week)

    async def get_current_open_week(self) -> WeekResponse | None:
        """Return the currently open week, if any."""
        week = await self._week_repo.get_current_open_week()
        if week is None:
            return None
        return WeekResponse.model_validate(week)

    async def get_relevant_week_with_days(self) -> WeekWithDaysResponse | None:
        """Return the week guards should see, with its status.

        Resolution order (most relevant to the guard first):
          1. The OPEN week — where they can actually submit.
          2. The nearest week that has not ended yet (``end_date >= today``),
             so a locked *current* week wins over an already-created next week.
          3. The latest week overall — when every week has ended, show the most
             recent one (typically a published schedule).

        Returns ``None`` only when no week exists at all. The UI uses the status
        to render the right banner instead of a generic "no week" error.
        """
        week = await self._week_repo.get_current_open_week()
        if week is None:
            week = await self._week_repo.get_current_or_upcoming_week(today_il())
        if week is None:
            week = await self._week_repo.get_latest_week()
        if week is None:
            return None
        days = [DayItem(day_index=i, blocked=False) for i in range(7)]
        return WeekWithDaysResponse(
            id=week.id,
            start_date=week.start_date,
            end_date=week.end_date,
            status=week.status,
            days=days,
        )

    async def get_latest_week(self) -> WeekResponse | None:
        """Return the most recent week (by start_date), regardless of status."""
        week = await self._week_repo.get_latest_week()
        if week is None:
            return None
        return WeekResponse.model_validate(week)

    async def validate_week_is_open(self, week_id: uuid.UUID) -> None:
        """Raise WeekLockedException if the week is not open."""
        week = await self._get_week_or_raise(week_id)
        if week.status != WeekStatus.OPEN:
            logger.warning(f"Week {week_id} is {week.status}, not open")
            raise WeekLockedException()

    async def delete_week(self, week_id: uuid.UUID) -> None:
        """Delete a schedule week by ID.

        Only allows deletion of non-finalized weeks to preserve history.
        """
        week = await self._get_week_or_raise(week_id)
        if week.status == WeekStatus.LOCKED:
            raise InvalidTransitionException(
                "לא ניתן למחוק שבוע נעול — הוא חלק מההיסטוריה"
            )
        deleted = await self._week_repo.delete(week_id)
        if not deleted:
            from app.exceptions import UserNotFoundException
            raise UserNotFoundException()
        logger.info(f"Week {week_id} deleted (was {week.status})")

    async def auto_open_relevant_week(self) -> WeekResponse | None:
        """Open the upcoming closed week for submissions (cron entry point).

        Broadcasts to guards (``notify=True``). Idempotent and crash-safe:
          - if a week is already OPEN → no-op, returns ``None`` (don't open two).
          - if there is no upcoming CLOSED week → no-op (auto_rotate creates it).
          - any error is logged, never raised, so the cron job keeps running.

        Publishing stays manual — this only does closed → open.
        """
        try:
            existing_open = await self._week_repo.get_current_open_week()
            if existing_open is not None:
                logger.info(
                    "auto_open: a week is already open (id=%s) — skipping",
                    existing_open.id,
                )
                return None

            candidate = await self._week_repo.get_upcoming_closed_week(today_il())
            if candidate is None:
                logger.info("auto_open: no upcoming closed week to open — skipping")
                return None

            result = await self.change_week_status(
                candidate.id, WeekStatus.OPEN, notify=True
            )
            logger.info(
                "auto_open: opened week %s – %s (id=%s)",
                candidate.start_date,
                candidate.end_date,
                candidate.id,
            )
            return result
        except Exception as exc:
            logger.warning("auto_open_relevant_week failed: %s", exc)
            return None

    @staticmethod
    def _last_weekly_moment(
        now: datetime, weekday_token: str, hour: int, minute: int
    ) -> datetime:
        """Most recent datetime ``<= now`` on ``weekday_token`` at ``hour:minute``.

        ``weekday_token`` is an APScheduler day-of-week token ("sun".."sat").
        Used to locate the current cycle's auto-open / auto-lock boundaries.
        """
        target_wd = _PY_WEEKDAY.get(weekday_token, 6)
        delta = (now.weekday() - target_wd) % 7
        moment = (now - timedelta(days=delta)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if moment > now:  # the weekday matches today but the time hasn't arrived
            moment -= timedelta(days=7)
        return moment

    @staticmethod
    def _is_in_open_phase(now: datetime, auto_open: dict, auto_lock: dict) -> bool:
        """Whether ``now`` is inside the weekly window the target week should be OPEN.

        We are in the open phase when the most recent auto-open moment is more
        recent than the most recent auto-lock moment (the latest boundary we
        crossed was an open, not a lock). With auto-lock disabled the week stays
        open until the Sunday rollover, so any time after an auto-open counts.
        Returns False when auto-open is disabled.
        """
        if not auto_open.get("enabled"):
            return False
        open_moment = WeekService._last_weekly_moment(
            now, auto_open["weekday"], auto_open["hour"], auto_open["minute"]
        )
        if auto_lock.get("enabled"):
            lock_moment = WeekService._last_weekly_moment(
                now, auto_lock["weekday"], auto_lock["hour"], auto_lock["minute"]
            )
            return open_moment > lock_moment
        return True

    @staticmethod
    def _is_in_lock_phase(now: datetime, auto_open: dict, auto_lock: dict) -> bool:
        """Whether ``now`` is inside the weekly window the target week should be CLOSED.

        The exact complement of ``_is_in_open_phase`` when both automations are
        enabled: we are in the lock phase when the most recent auto-lock moment
        is more recent than the most recent auto-open moment (the latest boundary
        we crossed was a lock, not an open).

        Requires BOTH auto-open and auto-lock enabled. Auto-lock alone has no
        recurring open boundary to bound the window on the left, so it can't be
        caught up safely (unlike open, which self-limits to a never-opened week
        via ``opened_at``; the lock catch-up would otherwise re-close and
        re-broadcast on every load after a manual reopen). Returns False when
        either is disabled.
        """
        if not auto_lock.get("enabled") or not auto_open.get("enabled"):
            return False
        lock_moment = WeekService._last_weekly_moment(
            now, auto_lock["weekday"], auto_lock["hour"], auto_lock["minute"]
        )
        open_moment = WeekService._last_weekly_moment(
            now, auto_open["weekday"], auto_open["hour"], auto_open["minute"]
        )
        return lock_moment > open_moment

    async def auto_open_if_due(self) -> WeekResponse | None:
        """Catch-up auto-open for the self-heal / startup path.

        The scheduled auto-open cron fires once a week; if that single firing is
        missed (deploy, restart, or a transient failure in the 00:00 rollover
        that leaves no week for the 01:00 open to act on), nothing else opens the
        week — unlike lock/rotate/purge, which self-heal on every weeks-list load.
        This closes that gap: whenever we are inside the configured weekly open
        window and the target week is still closed, open it.

        The open window is computed in ``SCHEDULER_TIMEZONE`` (not the server's
        UTC date) so the boundary is correct across midnight. Idempotent — it
        delegates to ``auto_open_relevant_week``, which no-ops when a week is
        already OPEN or there is no never-opened candidate, so it opens (and
        broadcasts) at most once per cycle. Errors are logged, never raised.
        """
        try:
            from app.repositories.system_settings_repository import (
                SystemSettingsRepository,
            )
            from app.services.settings_service import SettingsService

            settings_service = SettingsService(
                SystemSettingsRepository(self._week_repo.session)
            )
            auto_open = await settings_service.get_auto_open()
            if not auto_open.get("enabled"):
                return None
            auto_lock = await settings_service.get_auto_lock()

            now = now_il()
            if not self._is_in_open_phase(now, auto_open, auto_lock):
                return None

            return await self.auto_open_relevant_week()
        except Exception as exc:
            logger.warning("auto_open_if_due failed: %s", exc)
            return None

    async def auto_lock_if_due(self) -> WeekResponse | None:
        """Catch-up auto-lock for the self-heal / startup path.

        Mirror of ``auto_open_if_due`` for the closing side. The scheduled
        auto-lock cron fires once a week; if that single firing is missed
        (server down at the lock time, deploy, restart), the week stays OPEN
        past its lock time with nothing to close it — the Sunday-rollover
        self-heal only finalizes weeks whose ``start_date`` has arrived, not a
        lock TIME earlier in the same cycle. This closes that gap: whenever we
        are inside the configured weekly lock window and a week is still OPEN,
        close its submission window.

        The window is computed in ``SCHEDULER_TIMEZONE`` so the boundary is
        correct across midnight. Idempotent — it delegates to
        ``auto_lock_open_week``, which no-ops when there is no OPEN week, so it
        closes (and broadcasts) at most once per cycle. Errors are logged,
        never raised.
        """
        try:
            from app.repositories.system_settings_repository import (
                SystemSettingsRepository,
            )
            from app.services.settings_service import SettingsService

            settings_service = SettingsService(
                SystemSettingsRepository(self._week_repo.session)
            )
            auto_lock = await settings_service.get_auto_lock()
            if not auto_lock.get("enabled"):
                return None
            auto_open = await settings_service.get_auto_open()

            now = now_il()
            if not self._is_in_lock_phase(now, auto_open, auto_lock):
                return None

            return await self.auto_lock_open_week()
        except Exception as exc:
            logger.warning("auto_lock_if_due failed: %s", exc)
            return None

    async def auto_lock_open_week(self) -> WeekResponse | None:
        """Close the currently open week's submission window (cron entry point).

        Transitions OPEN → CLOSED (reopenable) with ``notify=False`` — the
        scheduled lock TIME ends submissions but the week stays editable by an
        admin and can be reopened; it is finalized to LOCKED only by the Sunday
        rollover. Idempotent and crash-safe: no open week → no-op; terminal
        weeks are never touched (only an OPEN week is selected); errors are
        logged, not raised. (Job id stays ``auto_lock_week`` for settings stability.)
        """
        try:
            week = await self._week_repo.get_current_open_week()
            if week is None:
                logger.info("auto_lock: no open week — skipping")
                return None

            result = await self.change_week_status(
                week.id, WeekStatus.CLOSED, notify=False
            )
            logger.info(
                "auto_lock: closed submission window for week %s – %s (id=%s)",
                week.start_date,
                week.end_date,
                week.id,
            )

            # Broadcast the lock notice. ``change_week_status`` only notifies on
            # OPEN/LOCKED, so the CLOSED auto-lock is announced here — and only
            # for the scheduled lock, not every manual transition to CLOSED.
            try:
                telegram_ids: list[int] = []
                if self._user_repo is not None:
                    users = await self._user_repo.get_all()
                    telegram_ids = [u.telegram_id for u in users if u.telegram_id]
                if telegram_ids:
                    from app.bot.notifications import notify_week_closed

                    await notify_week_closed(
                        result.start_date, result.end_date, telegram_ids
                    )
            except Exception as exc:
                logger.warning("auto_lock: failed to send lock notification: %s", exc)

            return result
        except Exception as exc:
            logger.warning("auto_lock_open_week failed: %s", exc)
            return None

    async def auto_advance_weeks(self) -> None:
        """Perform the automatic weekly rollover (idempotent, self-healing).

        This is the single entry point for the Saturday-night (Motzaei Shabbat,
        Sunday 00:00) rollover. It runs on a scheduled trigger, on startup, and
        on every weeks-list load, and converges to the correct state regardless
        of how many times it runs:

          1. Lock any OPEN week whose ``start_date`` has arrived — it is the
             week that just became "current" and is no longer a relevant
             submission target (``lock_expired_open_weeks``).
          2. Ensure the upcoming Sun–Sat week exists as CLOSED so the admin has
             a next week ready to open (``auto_rotate_weeks``).
          3. Purge weeks older than the retention window so the database keeps
             only the most recent ``RETENTION_WEEKS`` weeks (``purge_old_weeks``).

        Because the lock rule keys on ``start_date <= today``, a missed run
        (server down at midnight) is corrected automatically on the next call —
        no catch-up bookkeeping needed.
        """
        await self.lock_expired_open_weeks()
        await self.auto_rotate_weeks()
        await self.auto_open_if_due()
        await self.auto_lock_if_due()
        await self.purge_old_weeks()

    async def lock_expired_open_weeks(self) -> None:
        """Finalize started weeks to LOCKED at the Sunday rollover.

        The moment a week's ``start_date`` arrives it is no longer a relevant
        submission target, so the rollover finalizes it OPEN/CLOSED → LOCKED
        **silently** (no Telegram broadcast at midnight). LOCKED is the final,
        non-reopenable state. **Every** started, not-yet-locked week is
        finalized regardless of state — OPEN, CLOSED-that-ran, or a CLOSED week
        that was never opened — so a stale ghost week left behind by a skipped
        cycle can no longer stay editable forever. Only future weeks
        (``start_date > today``) and already-LOCKED weeks are left untouched.
        """
        today = today_il()
        try:
            stale = await self._week_repo.get_weeks_to_finalize_on_or_before(today)
        except Exception as exc:
            logger.warning(f"Failed to query weeks to finalize: {exc}")
            return

        for week in stale:
            try:
                await self.change_week_status(
                    week.id, WeekStatus.LOCKED, notify=False
                )
                logger.info(
                    f"Rollover finalized week {week.start_date} – "
                    f"{week.end_date} to LOCKED (id={week.id})"
                )
            except Exception as exc:
                logger.warning(f"Failed to finalize week {week.id}: {exc}")
                continue
            # The planning board just froze — birth the week's editable
            # execution copy (actual schedule). Best-effort: a failure (or a
            # path constructed without the seeder) is healed by the lazy seed
            # on first read.
            if self._actual_schedule is not None:
                try:
                    await self._actual_schedule.ensure_for_week(
                        week.id, source="rollover"
                    )
                except Exception as exc:
                    logger.warning(
                        f"Failed to seed actual schedule for week {week.id}: {exc}"
                    )

    async def auto_rotate_weeks(self) -> None:
        """Ensure the upcoming week always exists, created CLOSED.

        Runs on every weeks-list load and on startup. It does NOT change the
        status of existing weeks — every transition (open / lock / publish) is a
        deliberate admin action. Its single job: if no week exists yet for the
        upcoming Sun–Sat range, create it as CLOSED so the admin always has a
        next week ready to open.

        Dedup is by date range (``get_by_date_range``), so it never duplicates an
        already-existing upcoming week. This is now the ONLY path that creates the
        next week — publish no longer does.
        """
        today = today_il()
        ws, we = week_range(today)  # upcoming Sunday..Saturday

        try:
            existing = await self._week_repo.get_by_date_range(ws, we)
            if existing is None:
                new_week = ScheduleWeek(
                    start_date=ws,
                    end_date=we,
                    status=WeekStatus.CLOSED,
                )
                created = await self._week_repo.save(new_week)
                logger.info(
                    f"Auto-created upcoming week (closed): {ws} – {we} (id={created.id})"
                )
        except Exception as exc:
            logger.warning(f"Failed to auto-create upcoming week: {exc}")

    async def purge_old_weeks(self) -> int:
        """Delete weeks older than the retention window. Returns the count purged.

        Keeps only the most recent ``RETENTION_WEEKS`` weeks (by ``start_date``)
        and hard-deletes everything older — **including locked/finalized weeks**, since
        the whole point of the retention cap is to bound how much history is
        kept. Children (submissions → daily statuses → shift windows) are removed
        by the ``ON DELETE CASCADE`` chain at the database level.

        Idempotent and self-healing: once the DB holds ≤ retention weeks it is a
        no-op, so it is safe to run on every rollover / weeks-list load. Failures
        are logged and swallowed so they never break the rollover.
        """
        from app.config import get_settings

        settings = get_settings()
        if not settings.RETENTION_ENABLED:
            return 0

        try:
            stale = await self._week_repo.get_weeks_beyond_retention(
                settings.RETENTION_WEEKS
            )
        except Exception as exc:
            logger.warning(f"Failed to query weeks beyond retention: {exc}")
            return 0

        purged = 0
        for week in stale:
            try:
                # Delete directly (not delete_week) to bypass the locked-week guard:
                # purging old history is the intended behavior here.
                deleted = await self._week_repo.delete(week.id)
                if deleted:
                    purged += 1
                    logger.info(
                        f"Purged old week {week.start_date} – {week.end_date} "
                        f"(id={week.id}, was {week.status})"
                    )
            except Exception as exc:
                logger.warning(f"Failed to purge week {week.id}: {exc}")

        if purged:
            logger.info(
                f"Retention purge removed {purged} week(s); "
                f"keeping the most recent {settings.RETENTION_WEEKS}"
            )
        return purged

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _get_week_or_raise(self, week_id: uuid.UUID) -> ScheduleWeek:
        """Fetch week or raise WeekLockedException as a proxy for not-found."""
        week = await self._week_repo.get_by_id(week_id)
        if week is None:
            from app.exceptions import UserNotFoundException
            raise UserNotFoundException()
        return week