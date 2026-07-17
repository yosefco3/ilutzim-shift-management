"""
Question generation service + the generate endpoint.

The Anthropic SDK is mocked (no network). Covers: success, missing key → 503,
API failure → 503, malformed/empty output, per-item validation, and that
regeneration preserves admin-edited AI questions + manual questions.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.exceptions import ValidationException
from app.procedures.constants import ProcedureStatus, QuestionSource
from app.procedures.controllers.procedure_controller import router as procedures_router
from app.procedures.repositories import ProcedureRepository, QuizQuestionRepository
from app.procedures.services.question_generation_service import (
    GenerationUnavailableException,
    QuestionGenerationService,
    _QuestionBank,
    _QuestionItem,
)
from app.procedures.services.question_service import QuizQuestionService


# ── Fake Anthropic client ────────────────────────────────────────────────────


class _FakeMessages:
    def __init__(self, parsed_output=None, exc=None):
        self.parsed_output = parsed_output
        self.exc = exc
        self.parse = AsyncMock(side_effect=self._parse)

    async def _parse(self, **kwargs):
        if self.exc is not None:
            raise self.exc
        return SimpleNamespace(parsed_output=self.parsed_output)


class _FakeClient:
    def __init__(self, parsed_output=None, exc=None):
        self.messages = _FakeMessages(parsed_output=parsed_output, exc=exc)


def _bank(*items):
    return _QuestionBank(questions=[_QuestionItem(**i) for i in items])


def _settings_with(key_value):
    return MagicMock(ANTHROPIC_API_KEY=key_value)


def _gen(client):
    """A generation service wired to a fake client + a non-None key."""
    svc = QuestionGenerationService(client_factory=lambda _k: client)
    svc._module = None
    return svc


# ── Service: happy path + validation ────────────────────────────────────────


async def test_generate_success_returns_validated_items(monkeypatch):
    from app.procedures.services import question_generation_service as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _settings_with("k"))
    client = _FakeClient(parsed_output=_bank(
        {"text": "מה עושים?", "options": ["א", "ב", "ג", "ד"], "correct_index": 1},
        {"text": "כמה יוצאים?", "options": ["1", "2", "3", "4"], "correct_index": 0},
    ))
    items = await QuestionGenerationService(client_factory=lambda _k: client).generate("body", "claude-opus-4-8")
    assert len(items) == 2
    assert items[0]["correct_index"] == 1
    assert items[0]["options"] == ["א", "ב", "ג", "ד"]
    # the SDK call passed the structured-output Pydantic model + the setting model
    call_kwargs = client.messages.parse.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-8"
    assert call_kwargs["output_format"] is _QuestionBank


async def test_generate_drops_invalid_items(monkeypatch):
    """Items with wrong option count / bad index are dropped; valid kept."""
    from app.procedures.services import question_generation_service as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _settings_with("k"))
    client = _FakeClient(parsed_output=_bank(
        {"text": "תקין", "options": ["a", "b", "c", "d"], "correct_index": 0},
        {"text": "רק אחת", "options": ["a"], "correct_index": 0},  # too few (<2) -> dropped
        {"text": "אינדקס רע", "options": ["a", "b", "c", "d"], "correct_index": 9},  # bad idx
    ))
    items = await QuestionGenerationService(client_factory=lambda _k: client).generate("body", "m")
    assert len(items) == 1
    assert items[0]["text"] == "תקין"


async def test_generate_truncates_overlong_fields(monkeypatch):
    from app.procedures.services import question_generation_service as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _settings_with("k"))
    long_q = "x" * 500
    long_o = "y" * 200
    client = _FakeClient(parsed_output=_bank(
        {"text": long_q, "options": [long_o, "b", "c", "d"], "correct_index": 0},
    ))
    items = await QuestionGenerationService(client_factory=lambda _k: client).generate("body", "m")
    assert len(items[0]["text"]) == 300  # MAX_QUESTION_CHARS
    assert all(len(o) <= 100 for o in items[0]["options"])


# ── Service: failure modes → 503 ────────────────────────────────────────────


async def test_generate_missing_key_raises_503(monkeypatch):
    from app.procedures.services import question_generation_service as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _settings_with(None))
    svc = QuestionGenerationService(client_factory=lambda _k: _FakeClient())
    with pytest.raises(GenerationUnavailableException) as exc_info:
        await svc.generate("body", "m")
    assert exc_info.value.status_code == 503


async def test_generate_api_failure_raises_503(monkeypatch):
    from app.procedures.services import question_generation_service as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _settings_with("k"))
    client = _FakeClient(exc=RuntimeError("timeout"))
    svc = QuestionGenerationService(client_factory=lambda _k: client)
    with pytest.raises(GenerationUnavailableException):
        await svc.generate("body", "m")


async def test_generate_no_parsed_output_raises_503(monkeypatch):
    from app.procedures.services import question_generation_service as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _settings_with("k"))
    client = _FakeClient(parsed_output=None)
    svc = QuestionGenerationService(client_factory=lambda _k: client)
    with pytest.raises(GenerationUnavailableException):
        await svc.generate("body", "m")


async def test_generate_all_invalid_raises_503(monkeypatch):
    from app.procedures.services import question_generation_service as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _settings_with("k"))
    client = _FakeClient(parsed_output=_bank(
        {"text": "", "options": ["a", "b", "c", "d"], "correct_index": 0},  # empty text
    ))
    svc = QuestionGenerationService(client_factory=lambda _k: client)
    with pytest.raises(GenerationUnavailableException):
        await svc.generate("body", "m")


# ── Regeneration preserves edited AI + manual questions ──────────────────────


async def test_regenerate_preserves_edited_and_manual_questions(db_session):
    proc_repo = ProcedureRepository(db_session)
    q_repo = QuizQuestionRepository(db_session)
    qsvc = QuizQuestionService(q_repo, proc_repo)

    from app.procedures.models import Procedure, QuizQuestion

    proc = Procedure(title="נהל", body_text="תוכן", status=ProcedureStatus.DRAFT)
    db_session.add(proc)
    await db_session.flush()

    import uuid as _uuid
    from datetime import datetime, timezone

    ai_unedited = QuizQuestion(
        procedure_id=proc.id, text="ai1", options=["a", "b", "c", "d"],
        correct_index=0, display_order=0, source=QuestionSource.AI,
    )
    ai_edited = QuizQuestion(
        procedure_id=proc.id, text="ai2", options=["a", "b", "c", "d"],
        correct_index=0, display_order=1, source=QuestionSource.AI,
        edited_at=datetime.now(timezone.utc),
    )
    manual = QuizQuestion(
        procedure_id=proc.id, text="manual", options=["a", "b", "c", "d"],
        correct_index=0, display_order=2, source=QuestionSource.MANUAL,
    )
    db_session.add_all([ai_unedited, ai_edited, manual])
    await db_session.commit()

    new_items = [
        {"text": "new1", "options": ["a", "b", "c", "d"], "correct_index": 0},
        {"text": "new2", "options": ["a", "b", "c", "d"], "correct_index": 1},
    ]
    created, deleted = await qsvc.regenerate(proc.id, new_items)
    await db_session.commit()

    assert created == 2
    assert deleted == 1  # only ai_unedited removed
    remaining = await q_repo.list_for_procedure(proc.id)
    texts = sorted(q.text for q in remaining)
    assert texts == ["ai2", "manual", "new1", "new2"]


async def test_regenerate_only_while_draft(db_session):
    from app.procedures.models import Procedure

    proc = Procedure(title="נהל", body_text="תוכן", status=ProcedureStatus.PUBLISHED)
    db_session.add(proc)
    await db_session.commit()
    qsvc = QuizQuestionService(QuizQuestionRepository(db_session), ProcedureRepository(db_session))
    from app.exceptions import ConflictException

    with pytest.raises(ConflictException):
        await qsvc.regenerate(proc.id, [{"text": "x", "options": ["a", "b"], "correct_index": 0}])


# ── Generate endpoint (controller wiring, all deps faked) ────────────────────


def _client(
    *,
    procedure=None,
    generated=None,
    draft=True,
    regenerate=None,
    settings=None,
    gen_svc=None,
):
    from app.dependencies import require_admin_role
    from app.procedures.dependencies import (
        get_generation_service,
        get_procedure_service,
        get_question_repo,
        get_question_service,
        get_settings_service,
    )

    app = FastAPI()
    app.include_router(procedures_router)
    app.dependency_overrides[require_admin_role] = lambda: None

    proc = MagicMock()
    proc.status.value = "draft" if draft else "published"
    proc.body_text = "body"
    proc.questions = []

    proc_svc = MagicMock()
    proc_svc.get = AsyncMock(return_value=proc)

    if gen_svc is None:
        gen_svc = MagicMock()
        gen_svc.generate = AsyncMock(return_value=generated if generated is not None else [])

    q_svc = MagicMock()
    q_svc.regenerate = AsyncMock(return_value=regenerate or (0, 0))

    q_repo = MagicMock()
    q_repo.count_all = AsyncMock(return_value=5)

    if settings is None:
        settings = MagicMock()
        settings.get_setting = AsyncMock(return_value="claude-opus-4-8")

    app.dependency_overrides[get_procedure_service] = lambda: proc_svc
    app.dependency_overrides[get_generation_service] = lambda: gen_svc
    app.dependency_overrides[get_question_service] = lambda: q_svc
    app.dependency_overrides[get_question_repo] = lambda: q_repo
    app.dependency_overrides[get_settings_service] = lambda: settings
    return TestClient(app)


def test_generate_endpoint_returns_counts():
    client = _client(
        generated=[{"text": "q", "options": ["a", "b", "c", "d"], "correct_index": 0}],
        regenerate=(1, 0),
    )
    res = client.post("/admin/procedures/00000000-0000-0000-0000-000000000001/generate")
    assert res.status_code == 200
    body = res.json()
    assert body["generated"] == 1
    assert body["total_questions"] == 5


def test_generate_endpoint_409_when_not_draft():
    client = _client(draft=False)
    res = client.post("/admin/procedures/00000000-0000-0000-0000-000000000001/generate")
    assert res.status_code == 409


# ── Bank size: prompt + clamping + controller wiring ─────────────────────────


def _prompt_passed_to(client):
    """The user prompt the generation call sent to Claude."""
    content = client.messages.parse.call_args.kwargs["messages"][0]["content"]
    return content


async def test_generate_prompt_asks_for_exact_bank_size(monkeypatch):
    from app.procedures.services import question_generation_service as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _settings_with("k"))
    client = _FakeClient(parsed_output=_bank(
        {"text": "q", "options": ["a", "b", "c", "d"], "correct_index": 0},
    ))
    await QuestionGenerationService(client_factory=lambda _k: client).generate(
        "body", "m", bank_size=12
    )
    prompt = _prompt_passed_to(client)
    assert "בדיוק 12 שאלות" in prompt
    assert "בין 15 ל-20" not in prompt  # the old hardcoded phrasing is gone


async def test_generate_clamps_bank_size_into_prompt(monkeypatch):
    from app.procedures.services import question_generation_service as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _settings_with("k"))
    # (raw setting value → clamped count asserted in the prompt)
    cases = [(100, "40"), (1, "5"), ("garbage", "20"), (None, "20"), (25, "25")]
    for raw, expected in cases:
        client = _FakeClient(parsed_output=_bank(
            {"text": "q", "options": ["a", "b", "c", "d"], "correct_index": 0},
        ))
        await QuestionGenerationService(client_factory=lambda _k: client).generate(
            "body", "m", bank_size=raw
        )
        assert f"בדיוק {expected} שאלות" in _prompt_passed_to(client)


def test_coerce_bank_size_clamps_and_defaults():
    from app.procedures.services.question_generation_service import _coerce_bank_size

    assert _coerce_bank_size(100) == 40
    assert _coerce_bank_size(1) == 5
    assert _coerce_bank_size(40) == 40
    assert _coerce_bank_size(5) == 5
    assert _coerce_bank_size(20) == 20
    assert _coerce_bank_size(25) == 25
    assert _coerce_bank_size("30") == 30
    assert _coerce_bank_size("garbage") == 20
    assert _coerce_bank_size(None) == 20


def test_generate_endpoint_passes_bank_size_setting():
    """The controller reads procedure_bank_size and forwards it to generate()."""
    async def fake_get(key):
        if key == "procedure_ai_model":
            return "claude-opus-4-8"
        if key == "procedure_bank_size":
            return 33
        return None

    settings = MagicMock()
    settings.get_setting = AsyncMock(side_effect=fake_get)

    gen_svc = MagicMock()
    gen_svc.generate = AsyncMock(return_value=[
        {"text": "q", "options": ["a", "b", "c", "d"], "correct_index": 0},
    ])

    client = _client(settings=settings, gen_svc=gen_svc, regenerate=(1, 0))
    res = client.post("/admin/procedures/00000000-0000-0000-0000-000000000001/generate")
    assert res.status_code == 200
    gen_svc.generate.assert_awaited_once()
    assert gen_svc.generate.call_args.kwargs["bank_size"] == 33
