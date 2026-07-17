"""
Procedure-quiz dependency providers (same boundary role as
``app.attendance.dependencies``): procedures may import from part A; nothing
imports back (except the conditional registration points in main.py / bot_router
/ scheduler).
"""

from fastapi import Depends

from app.database import get_pool
from app.procedures.repositories.attempt_repository import QuizAttemptRepository
from app.procedures.repositories.poll_link_repository import QuizPollLinkRepository
from app.procedures.repositories.procedure_repository import ProcedureRepository
from app.procedures.repositories.question_repository import QuizQuestionRepository
from app.procedures.repositories.reminder_repository import (
    ProcedureReminderRepository,
)
from app.procedures.services.procedure_service import ProcedureService
from app.procedures.services.publish_service import RealProcedurePublisher
from app.procedures.services.question_generation_service import (
    QuestionGenerationService,
)
from app.procedures.services.question_service import QuizQuestionService
from app.procedures.services.quiz_service import QuizService
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.repositories.user_repository import UserRepository
from app.services.settings_service import SettingsService


# ── Repositories ─────────────────────────────────────────────────────────────


async def get_procedure_repo(session=Depends(get_pool)) -> ProcedureRepository:
    return ProcedureRepository(session)


async def get_question_repo(session=Depends(get_pool)) -> QuizQuestionRepository:
    return QuizQuestionRepository(session)


async def get_attempt_repo(session=Depends(get_pool)) -> QuizAttemptRepository:
    return QuizAttemptRepository(session)


async def get_poll_link_repo(session=Depends(get_pool)) -> QuizPollLinkRepository:
    return QuizPollLinkRepository(session)


async def get_reminder_repo(
    session=Depends(get_pool),
) -> ProcedureReminderRepository:
    return ProcedureReminderRepository(session)


def _settings(session) -> SettingsService:
    return SettingsService(SystemSettingsRepository(session))


def _start_quiz_keyboard_factory():
    """A factory that builds the start-quiz inline keyboard, lazily importing the
    bot keyboard module so this dependency layer never imports the bot at load."""

    def factory(procedure_id):
        from app.bot.keyboards.procedures import start_quiz_kb

        return start_quiz_kb(str(procedure_id))

    return factory


# ── Services ─────────────────────────────────────────────────────────────────


async def get_procedure_service(
    session=Depends(get_pool),
) -> ProcedureService:
    return ProcedureService(
        ProcedureRepository(session),
        QuizQuestionRepository(session),
        QuizAttemptRepository(session),
        UserRepository(session),
        _settings(session),
        RealProcedurePublisher(keyboard_factory=_start_quiz_keyboard_factory()),
    )


async def get_question_service(
    session=Depends(get_pool),
) -> QuizQuestionService:
    return QuizQuestionService(
        QuizQuestionRepository(session),
        ProcedureRepository(session),
    )


async def get_quiz_service(session=Depends(get_pool)) -> QuizService:
    return QuizService(
        ProcedureRepository(session),
        QuizQuestionRepository(session),
        QuizAttemptRepository(session),
        QuizPollLinkRepository(session),
        _settings(session),
    )


async def get_generation_service() -> QuestionGenerationService:
    # client_factory=None → uses the real AsyncAnthropic client (key validated
    # at call time). Tests override this dependency with a mock factory.
    return QuestionGenerationService()


async def get_settings_service(session=Depends(get_pool)) -> SettingsService:
    return _settings(session)


# ── Plain builders (scheduler / bot, hold their own session) ─────────────────


def build_quiz_service(session) -> QuizService:
    return QuizService(
        ProcedureRepository(session),
        QuizQuestionRepository(session),
        QuizAttemptRepository(session),
        QuizPollLinkRepository(session),
        _settings(session),
    )


def build_reminder_service(session, send) -> "ProcedureReminderService":
    from app.procedures.services.reminder_service import ProcedureReminderService

    return ProcedureReminderService(
        ProcedureRepository(session),
        QuizAttemptRepository(session),
        ProcedureReminderRepository(session),
        UserRepository(session),
        send,
    )
