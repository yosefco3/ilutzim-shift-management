"""
ProcedureReminderService — the one-time "you haven't done the quiz" reminder.

Daily job logic: targets ONLY the default procedure (הנוהל הנוכחי). If it is
PUBLISHED and older than ``REMINDER_AGE_HOURS``, remind each active
non-reinforcement guard (with a Telegram id) who hasn't passed and hasn't already
been reminded — once. Idempotent and crash-safe via the ``ProcedureReminderSent``
ledger: the row is written BEFORE the send, so a retry after a crash can never
duplicate a reminder (the cost of a crash between the record and the send is one
guard missing a single reminder — they can still reach the quiz from the menu).
No default procedure → no reminders at all.
"""

import logging
from datetime import datetime, timedelta

from app.procedures.constants import ProcedureStatus, REMINDER_AGE_HOURS
from app.procedures.services.quiz_window import is_quiz_open
from app.procedures.repositories.attempt_repository import QuizAttemptRepository
from app.procedures.repositories.procedure_repository import ProcedureRepository
from app.procedures.repositories.reminder_repository import ProcedureReminderRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger("ilutzim")


class ProcedureReminderService:
    """Sends at most one reminder per guard per (default) procedure."""

    def __init__(
        self,
        procedure_repo: ProcedureRepository,
        attempt_repo: QuizAttemptRepository,
        reminder_repo: ProcedureReminderRepository,
        user_repo: UserRepository,
        send,
    ) -> None:
        self._procedures = procedure_repo
        self._attempts = attempt_repo
        self._reminders = reminder_repo
        self._users = user_repo
        self._send = send  # send(telegram_id, procedure_id, title) -> bool

    async def run(self, now: datetime, window_days: int = 0) -> int:
        """Send reminders due as of ``now``. Returns the number sent.

        ``window_days`` is the current ``procedure_quiz_window_days`` setting
        (0 = unlimited) — an expired quiz gets no "go take the quiz" nudge.
        [EDGE D3]
        """
        cutoff = now - timedelta(hours=REMINDER_AGE_HOURS)
        proc = await self._procedures.get_default()
        # No default, or the default isn't a live published procedure older than
        # the age gate, or its availability window already closed → nothing to
        # remind about.
        if (
            proc is None
            or proc.status != ProcedureStatus.PUBLISHED
            or proc.published_at is None
            or proc.published_at > cutoff
            or not is_quiz_open(proc, window_days, now)
        ):
            return 0

        users = await self._users.get_active_users()
        sent_total = 0
        for user in users:
            if not user.telegram_id:
                continue
            if await self._attempts.has_passed(user.id, proc.id):
                continue
            # Record-first: the unique (procedure, user) row makes a retry
            # after a crash a no-op rather than a duplicate reminder.
            recorded = await self._reminders.record_or_skip(proc.id, user.id, now)
            if not recorded:
                continue
            if await self._send(user.telegram_id, proc.id, proc.title):
                sent_total += 1

        if sent_total:
            logger.info("Procedure reminders sent: %d", sent_total)
        return sent_total
