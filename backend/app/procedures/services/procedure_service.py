"""
ProcedureService — procedure lifecycle, publish, and results.

Layering: this orchestrates repositories + settings + a ``ProcedurePublisher``.
The publish fan-out is synchronous (see ``publish_service``) and runs behind the
injected publisher seam so tests assert counts without the bot.
"""

import logging
import uuid
from datetime import datetime

from app.exceptions import ConflictException, UserNotFoundException, ValidationException
from app.procedures.constants import ProcedureStatus
from app.procedures.repositories.attempt_repository import QuizAttemptRepository
from app.procedures.repositories.procedure_repository import ProcedureRepository
from app.procedures.repositories.question_repository import QuizQuestionRepository
from app.procedures.repositories.read_receipt_repository import (
    ProcedureReadReceiptRepository,
)
from app.procedures.services.publish_service import ProcedurePublisher
from app.procedures.services.quiz_window import is_quiz_open, quiz_deadline
from app.repositories.user_repository import UserRepository
from app.services.settings_service import SettingsService
from app.utils.date_utils import now_il

logger = logging.getLogger("ilutzim")


def _now_naive():
    return now_il().replace(tzinfo=None)


class ProcedureService:
    """Procedure CRUD + publish + per-guard results."""

    def __init__(
        self,
        procedure_repo: ProcedureRepository,
        question_repo: QuizQuestionRepository,
        attempt_repo: QuizAttemptRepository,
        user_repo: UserRepository,
        settings: SettingsService,
        publisher: ProcedurePublisher,
        read_receipt_repo: ProcedureReadReceiptRepository | None = None,
    ) -> None:
        self._procedures = procedure_repo
        self._questions = question_repo
        self._attempts = attempt_repo
        self._users = user_repo
        self._settings = settings
        self._publisher = publisher
        self._read_receipts = read_receipt_repo

    # ── CRUD ──────────────────────────────────────────────────────────────

    async def create(
        self,
        title: str,
        body_text: str,
        source_filename: str | None = None,
        body_html: str | None = None,
    ):
        proc = await self._procedures.create(
            title=title.strip(),
            body_text=body_text,
            body_html=body_html,
            source_filename=source_filename,
            status=ProcedureStatus.DRAFT,
        )
        logger.info("Procedure created: id=%s title=%r", proc.id, proc.title)
        return proc

    async def _window_days(self) -> int:
        """Current ``procedure_quiz_window_days`` (tolerant: bad value → 0)."""
        try:
            return int(await self._settings.get_setting("procedure_quiz_window_days"))
        except (TypeError, ValueError):
            return 0

    async def quiz_window_info(self, proc) -> tuple[bool, datetime | None]:
        """(quiz_open, quiz_deadline_at) for one procedure at the current setting.

        Meaningful for PUBLISHED procedures; a DRAFT has no anchor so it comes
        back (True, None) — the frontend gates on status anyway.
        """
        days = await self._window_days()
        return is_quiz_open(proc, days, _now_naive()), quiz_deadline(proc, days)

    async def list_all(self):
        """All procedures with active/total question counts for the list view."""
        procedures = await self._procedures.list_all()
        window_days = await self._window_days()
        now = _now_naive()
        rows = []
        for p in procedures:
            active = await self._questions.count_active(p.id)
            total = await self._questions.count_all(p.id)
            rows.append(
                {
                    "id": p.id,
                    "title": p.title,
                    "status": p.status.value,
                    "created_at": p.created_at,
                    "published_at": p.published_at,
                    "is_default": p.is_default,
                    "active_questions": active,
                    "total_questions": total,
                    # The UI hides the "generate with AI" button once a bank
                    # exists (accidental regeneration guard).
                    "has_ai_questions": (await self._questions.count_ai(p.id)) > 0,
                    # Availability window — the admin list shows a "המבחן סגור"
                    # badge on published rows whose window closed.
                    "quiz_open": is_quiz_open(p, window_days, now),
                    "quiz_deadline_at": quiz_deadline(p, window_days),
                }
            )
        return rows

    async def get(self, procedure_id: uuid.UUID):
        proc = await self._procedures.get_with_questions(procedure_id)
        if proc is None:
            raise UserNotFoundException("הנוהל לא נמצא")
        return proc

    # ── Guard WebApp view ─────────────────────────────────────────────

    async def guard_view(self, procedure_id: uuid.UUID, user) -> dict:
        """Return the procedure a guard reads in the WebApp page.

        PUBLISHED only — DRAFT / ARCHIVED / unknown id → 404 (no leak that a
        non-published procedure exists). Includes ``passed`` from the attempt
        repo and records the first-open read receipt **best-effort** (a receipt
        failure is logged and never breaks the view). [EDGE C1, D1]
        """
        proc = await self._procedures.get_by_id(procedure_id)
        if proc is None or proc.status != ProcedureStatus.PUBLISHED:
            raise UserNotFoundException("הנוהל אינו זמין יותר")

        passed = await self._attempts.has_passed(user.id, procedure_id)

        if self._read_receipts is not None:
            try:
                await self._read_receipts.record_first_read(
                    procedure_id, user.id, _now_naive()
                )
            except Exception as exc:  # noqa: BLE001 — best-effort: never fail the GET
                logger.warning(
                    "guard_view: read receipt failed for proc=%s user=%s — %s",
                    procedure_id, user.id, exc,
                )

        quiz_open, _ = await self.quiz_window_info(proc)
        return {
            "id": proc.id,
            "title": proc.title,
            "body_html": proc.body_html,
            "body_text": proc.body_text,
            "is_default": proc.is_default,
            "passed": passed,
            # False → the page hides the start-quiz button and explains why
            # (reading itself stays available — only the quiz is windowed).
            "quiz_open": quiz_open,
        }

    async def update(
        self,
        procedure_id: uuid.UUID,
        *,
        title: str | None,
        body_text: str | None,
        body_html: str | None = None,
    ):
        """Edit title/body (+ optional body_html snapshot) — DRAFT only.

        Omitting ``body_html`` (None) leaves the existing docx snapshot untouched
        — the admin plain-text editor edits only ``body_text`` and must not clear
        the snapshot ([EDGE D3]). Sending a new ``body_html`` (a re-upload)
        replaces it.
        """
        proc = await self._get_or_404(procedure_id)
        if proc.status != ProcedureStatus.DRAFT:
            raise ConflictException("ניתן לערוך נוהל טיוטה בלבד")
        fields: dict = {}
        if title is not None:
            fields["title"] = title.strip()
        if body_text is not None:
            fields["body_text"] = body_text
        if body_html is not None:
            fields["body_html"] = body_html
        if fields:
            return await self._procedures.update(procedure_id, **fields)
        return proc

    async def archive(self, procedure_id: uuid.UUID):
        """Retire a published procedure from the bot menu (history stays)."""
        proc = await self._get_or_404(procedure_id)
        if proc.status == ProcedureStatus.ARCHIVED:
            return proc
        return await self._procedures.update(
            procedure_id, status=ProcedureStatus.ARCHIVED
        )

    async def delete(self, procedure_id: uuid.UUID) -> None:
        """Hard-delete a procedure and ALL of its quiz history.

        Questions go via the ORM cascade; attempts, poll links, and reminder
        rows via the DB-level ``ON DELETE CASCADE``. This erases guards' scores
        for the procedure — the archive action is the keep-history alternative.
        Deleting the default procedure simply leaves no default until the next
        publish (reminders pause).
        """
        proc = await self._get_or_404(procedure_id)
        title, status = proc.title, proc.status.value
        await self._procedures.delete(procedure_id)
        logger.info(
            "Procedure deleted: id=%s title=%r status=%s (history erased)",
            procedure_id, title, status,
        )

    # ── Publish ───────────────────────────────────────────────────────────

    async def publish(self, procedure_id: uuid.UUID, *, rebroadcast: bool = False) -> dict:
        """Publish (or re-broadcast) a procedure to all guards.

          - DRAFT/ARCHIVED → set PUBLISHED + published_at, broadcast to ALL active
            non-reinforcement guards with a Telegram id.
          - PUBLISHED + no ``rebroadcast`` → 409 (already published).
          - PUBLISHED + ``rebroadcast`` → re-send to guards who have NOT passed
            only (no redundant noise to those who already passed).

        On every successful path this procedure also becomes the single default
        (the previous default is cleared atomically in the same transaction).

        Requires ≥ ``procedure_quiz_size`` active questions at publish time. The
        broadcast is synchronous and returns real ``{sent, skipped, total}``.
        """
        proc = await self._get_or_404(procedure_id)
        quiz_size = int(await self._settings.get_setting("procedure_quiz_size"))
        active = await self._questions.count_active(procedure_id)
        if active < quiz_size:
            raise ValidationException(
                f"נדרשות לפחות {quiz_size} שאלות פעילות לפרסום (יש {active})"
            )

        if proc.status == ProcedureStatus.PUBLISHED:
            if not rebroadcast:
                raise ConflictException("הנוהל כבר פורסם")
            # Rebroadcast re-opens the quiz: reset the availability-window
            # anchor (published_at stays — the reminder age-gate keys off it).
            proc = await self._procedures.update(
                procedure_id,
                quiz_window_started_at=_now_naive(),
            )
            republished = True
            recipients = await self._non_passed_recipients(procedure_id)
        else:
            now = _now_naive()
            proc = await self._procedures.update(
                procedure_id,
                status=ProcedureStatus.PUBLISHED,
                published_at=now,
                quiz_window_started_at=now,
            )
            republished = False
            recipients = await self._all_recipients()

        # Every successful publish path (first publish, archived re-publish, and
        # rebroadcast alike) makes this procedure the single default — atomically
        # and BEFORE the broadcast, so a crash mid-fan-out can't leave a stale
        # default. The reminder job + bot list then target the new default.
        proc = await self._procedures.set_as_default(procedure_id)

        summary = await self._publisher.broadcast(
            recipients, proc.title, procedure_id
        )
        return {**summary, "republished": republished}

    async def _all_recipients(self) -> list[str]:
        """Active non-reinforcement guards with a Telegram id."""
        users = await self._users.get_active_users()
        return [u.telegram_id for u in users if u.telegram_id]

    async def _non_passed_recipients(self, procedure_id: uuid.UUID) -> list[str]:
        """Active non-reinforcement guards with a Telegram id who haven't passed."""
        users = await self._users.get_active_users()
        recipients: list[str] = []
        for u in users:
            if not u.telegram_id:
                continue
            if await self._attempts.has_passed(u.id, procedure_id):
                continue
            recipients.append(u.telegram_id)
        return recipients

    # ── Results ───────────────────────────────────────────────────────────

    async def results(self, procedure_id: uuid.UUID) -> list[dict]:
        """Per-guard status for a procedure, excluding reinforcement guards.

        Buckets: passed / failed (best score) / in_progress ("התחיל, לא סיים") /
        not_started. ``attempts`` is the total attempts the guard made.
        """
        await self._get_or_404(procedure_id)
        users = await self._users.get_active_users()
        attempts = await self._attempts.list_for_procedure(procedure_id)
        by_user: dict[uuid.UUID, list] = {}
        for a in attempts:
            by_user.setdefault(a.user_id, []).append(a)

        # Per-guard read receipts: {user_id: first_read_at}. None when the repo
        # isn't wired (e.g. legacy tests) → every guard reports unread.
        read_map: dict = {}
        if self._read_receipts is not None:
            try:
                read_map = await self._read_receipts.read_map(procedure_id)
            except Exception as exc:  # noqa: BLE001 — defensive
                logger.warning("results: read_map failed for proc=%s — %s", procedure_id, exc)
                read_map = {}

        rows = []
        for u in users:
            row = self._result_row(u, by_user.get(u.id, []))
            first_read_at = read_map.get(u.id)
            row["read"] = first_read_at is not None
            row["first_read_at"] = first_read_at
            rows.append(row)
        return rows

    @staticmethod
    def _result_row(user, user_attempts) -> dict:
        total = len(user_attempts)
        finished = [a for a in user_attempts if a.correct_count is not None]
        best = max(
            (
                round(a.correct_count / a.total_count * 100) if a.total_count else 0
                for a in finished
            ),
            default=None,
        )
        passed = any(a.passed for a in user_attempts)
        in_progress = any(
            a.status and a.status.value == "in_progress" for a in user_attempts
        )
        if passed:
            status = "passed"
        elif finished:
            status = "failed"
        elif in_progress:
            status = "in_progress"
        else:
            status = "not_started"
        return {
            "user_id": user.id,
            "user_name": user.full_name,
            "status": status,
            "attempts": total,
            "best_score": best,
            "passed": passed if (passed or finished) else None,
        }

    # ── helpers ───────────────────────────────────────────────────────────

    async def _get_or_404(self, procedure_id: uuid.UUID):
        proc = await self._procedures.get_by_id(procedure_id)
        if proc is None:
            raise UserNotFoundException("הנוהל לא נמצא")
        return proc
