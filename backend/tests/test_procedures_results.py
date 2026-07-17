"""
Results endpoint buckets — passed / failed / in_progress / not_started, with
attempt counts and best score, excluding reinforcement guards.
"""

from datetime import datetime, timezone

from app.exceptions import UserNotFoundException
from app.models.user import User
from app.procedures.constants import AttemptStatus, ProcedureStatus, QuestionSource
from app.procedures.models import Procedure, QuizAttempt, QuizQuestion
from app.procedures.repositories import (
    ProcedureRepository,
    QuizAttemptRepository,
    QuizQuestionRepository,
)
from app.procedures.services.procedure_service import ProcedureService
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.repositories.user_repository import UserRepository
from app.services.settings_service import SettingsService


class _Pub:
    async def broadcast(self, recipients, title, body_text, procedure_id):
        return {"sent": 0, "skipped": 0, "total": 0}


def _svc(db_session) -> ProcedureService:
    return ProcedureService(
        ProcedureRepository(db_session),
        QuizQuestionRepository(db_session),
        QuizAttemptRepository(db_session),
        UserRepository(db_session),
        SettingsService(SystemSettingsRepository(db_session)),
        _Pub(),
    )


async def _setup(db_session):
    proc = Procedure(title="נהל", body_text="תוכן", status=ProcedureStatus.PUBLISHED)
    db_session.add(proc)
    await db_session.flush()
    db_session.add(QuizQuestion(
        procedure_id=proc.id, text="q", options=["a", "b", "c", "d"],
        correct_index=0, display_order=0, source=QuestionSource.AI,
    ))
    await db_session.commit()
    await db_session.refresh(proc)
    return proc


def _attempt(proc, user, *, correct, total, passed, status=AttemptStatus.FINISHED):
    return QuizAttempt(
        procedure_id=proc.id, user_id=user.id, question_ids=[str(i) for i in range(total)],
        answers={}, started_at=datetime.now(timezone.utc), total_count=total,
        correct_count=correct, passed=passed, status=status,
    )


async def test_results_buckets_and_exclusion(db_session):
    svc = _svc(db_session)
    proc = await _setup(db_session)

    passer = User(phone_number="0501111111", first_name="עבר", last_name="א", roles=[])
    failer = User(phone_number="0502222222", first_name="נכשל", last_name="ב", roles=[])
    inprog = User(phone_number="0503333333", first_name="אמצע", last_name="ג", roles=[])
    nothing = User(phone_number="0504444444", first_name="כלום", last_name="ד", roles=[])
    rein = User(phone_number="0505555555", first_name="מתגבר", last_name="ה",
                roles=[], is_reinforcement=True)
    db_session.add_all([passer, failer, inprog, nothing, rein])
    await db_session.flush()
    db_session.add_all([
        _attempt(proc, passer, correct=7, total=7, passed=True),
        _attempt(proc, passer, correct=5, total=7, passed=False),  # best is 100%
        _attempt(proc, failer, correct=3, total=7, passed=False),
        _attempt(proc, failer, correct=4, total=7, passed=False),  # best 57%
        QuizAttempt(
            procedure_id=proc.id, user_id=inprog.id, question_ids=["1", "2"],
            answers={"1": {"selected": 0, "correct": True}},
            started_at=datetime.now(timezone.utc), total_count=2,
            status=AttemptStatus.IN_PROGRESS,
        ),
    ])
    await db_session.commit()

    rows = {r["user_id"]: r for r in await svc.results(proc.id)}

    assert rows[passer.id]["status"] == "passed"
    assert rows[passer.id]["best_score"] == 100
    assert rows[passer.id]["attempts"] == 2

    assert rows[failer.id]["status"] == "failed"
    assert rows[failer.id]["best_score"] == 57
    assert rows[failer.id]["attempts"] == 2

    assert rows[inprog.id]["status"] == "in_progress"
    assert rows[inprog.id]["best_score"] is None

    assert rows[nothing.id]["status"] == "not_started"
    assert rows[nothing.id]["attempts"] == 0

    # reinforcement guard excluded entirely
    assert rein.id not in rows


async def test_results_unknown_procedure_404(db_session):
    import uuid

    svc = _svc(db_session)
    try:
        await svc.results(uuid.uuid4())
        assert False, "expected 404"
    except UserNotFoundException:
        pass
