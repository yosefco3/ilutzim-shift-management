"""
QuizQuestionService — the admin question-bank editor + regeneration.

After a procedure is published questions can be disabled or typo-edited but not
deleted (history by reference must stay valid); deletion is DRAFT-only.
Regeneration deletes ONLY ``source=AI AND edited_at IS NULL`` rows, so admin
edits and manual questions always survive a re-generate.
"""

import logging
import uuid
from datetime import datetime

from app.exceptions import ConflictException, UserNotFoundException, ValidationException
from app.procedures.constants import ProcedureStatus, QuestionSource
from app.procedures.repositories.procedure_repository import ProcedureRepository
from app.procedures.repositories.question_repository import QuizQuestionRepository
from app.utils.date_utils import now_il

logger = logging.getLogger("ilutzim")


class QuizQuestionService:
    """Admin editing of a procedure's question bank + AI regeneration."""

    def __init__(
        self,
        question_repo: QuizQuestionRepository,
        procedure_repo: ProcedureRepository,
    ) -> None:
        self._questions = question_repo
        self._procedures = procedure_repo

    async def add_manual(
        self,
        procedure_id: uuid.UUID,
        *,
        text: str,
        options: list[str],
        correct_index: int,
    ):
        """Append a manual question (source=MANUAL, always survives regeneration)."""
        await self._require_exists(procedure_id)
        order = await self._questions.next_display_order(procedure_id)
        return await self._questions.create(
            procedure_id=procedure_id,
            text=text,
            options=options,
            correct_index=correct_index,
            display_order=order,
            is_active=True,
            source=QuestionSource.MANUAL,
        )

    async def update(
        self,
        procedure_id: uuid.UUID,
        question_id: uuid.UUID,
        *,
        text=None,
        options=None,
        correct_index=None,
        is_active=None,
    ):
        """Edit a question. Any edit stamps ``edited_at`` (protects from deletion
        on regeneration). ``is_active`` may be flipped even after publish (disable
        instead of delete); textual edits after publish are allowed (typo fixes).
        """
        question = await self._get_owned(procedure_id, question_id)
        fields: dict = {}
        if text is not None:
            fields["text"] = text
        if options is not None:
            fields["options"] = options
        if correct_index is not None:
            fields["correct_index"] = correct_index
        if is_active is not None:
            fields["is_active"] = is_active
        if not fields:
            return question
        # Any edit marks the row as touched → it survives a later regeneration.
        fields["edited_at"] = now_il().replace(tzinfo=None)
        return await self._questions.update(question_id, **fields)

    async def delete(self, procedure_id: uuid.UUID, question_id: uuid.UUID) -> None:
        """Delete a question — DRAFT only (after publish, disable instead)."""
        proc = await self._require_exists(procedure_id)
        if proc.status != ProcedureStatus.DRAFT:
            raise ConflictException("לאחר פרסום ניתן להשבית שאלה, לא למחוק אותה")
        await self._get_owned(procedure_id, question_id)
        await self._questions.delete(question_id)

    async def regenerate(
        self, procedure_id: uuid.UUID, generated: list[dict]
    ) -> tuple[int, int]:
        """Replace the regenerable AI questions with ``generated``.

        Deletes only ``source=AI AND edited_at IS NULL`` rows, then appends the
        freshly generated AI questions. Admin-edited AI questions and all manual
        questions are preserved. Allowed only while DRAFT.

        Returns ``(created, deleted)``.
        """
        proc = await self._require_exists(procedure_id)
        if proc.status != ProcedureStatus.DRAFT:
            raise ConflictException("ניתן לחדש שאלות לנוהל טיוטה בלבד")
        if not generated:
            raise ValidationException("לא התקבלו שאלות ליצירה")

        deleted = await self._questions.delete_regenerable(procedure_id)
        base_order = await self._questions.next_display_order(procedure_id)
        created = 0
        for offset, item in enumerate(generated):
            await self._questions.create(
                procedure_id=procedure_id,
                text=item["text"],
                options=item["options"],
                correct_index=item["correct_index"],
                display_order=base_order + offset,
                is_active=True,
                source=QuestionSource.AI,
            )
            created += 1
        logger.info(
            "Procedure %s regenerated: %d created, %d deleted",
            procedure_id, created, deleted,
        )
        return created, deleted

    # ── helpers ───────────────────────────────────────────────────────────

    async def _require_exists(self, procedure_id: uuid.UUID):
        proc = await self._procedures.get_by_id(procedure_id)
        if proc is None:
            raise UserNotFoundException("הנוהל לא נמצא")
        return proc

    async def _get_owned(self, procedure_id: uuid.UUID, question_id: uuid.UUID):
        question = await self._questions.get_by_id(question_id)
        if question is None or question.procedure_id != procedure_id:
            raise UserNotFoundException("שאלה לא נמצאה")
        return question
