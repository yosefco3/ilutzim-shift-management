"""
Procedure-quiz API schemas (admin + internal shapes).

Validation mirrors the Telegram quiz-poll limits (question ≤ 300 chars, options
≤ 100 chars, 2–4 options) so an overlong/over-structured question is rejected at
the API boundary — never at send time in the bot.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.procedures.constants import (
    MAX_OPTIONS,
    MAX_OPTION_CHARS,
    MAX_QUESTION_CHARS,
    MIN_OPTIONS,
)


def _validate_question(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ValueError("טקסט השאלה ריק")
    if len(text) > MAX_QUESTION_CHARS:
        raise ValueError(f"טקסט השאלה ארוך מ-{MAX_QUESTION_CHARS} תווים")
    return text


def _validate_options(options: list[str]) -> list[str]:
    if options is None or len(options) < MIN_OPTIONS or len(options) > MAX_OPTIONS:
        raise ValueError(f"נדרשות בין {MIN_OPTIONS} ל-{MAX_OPTIONS} תשובות")
    cleaned = [(o or "").strip() for o in options]
    if any(len(o) > MAX_OPTION_CHARS for o in cleaned):
        raise ValueError(f"תשובה ארוכה מ-{MAX_OPTION_CHARS} תווים")
    if any(not o for o in cleaned):
        raise ValueError("אחת התשובות ריקה")
    return cleaned


def _validate_correct(correct_index: int, options: list[str]) -> int:
    if correct_index is None or correct_index < 0 or correct_index >= len(options):
        raise ValueError("correct_index מחוץ לטווח")
    return correct_index


# ── Procedure ────────────────────────────────────────────────────────────────


class ProcedureCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body_text: str = Field(min_length=1)


class ProcedureUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body_text: str | None = Field(default=None, min_length=1)


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    options: list[str]
    correct_index: int
    display_order: int
    is_active: bool
    source: str
    edited_at: datetime | None = None


class ProcedureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body_text: str
    source_filename: str | None = None
    status: str
    created_at: datetime
    published_at: datetime | None = None
    is_default: bool = False
    questions: list[QuestionOut] = Field(default_factory=list)


class ProcedureListItem(BaseModel):
    """One row of the admin procedure list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: str
    created_at: datetime
    published_at: datetime | None = None
    is_default: bool = False
    active_questions: int = 0
    total_questions: int = 0
    # True once an AI bank was generated — the UI hides the generate button.
    has_ai_questions: bool = False


# ── Questions ────────────────────────────────────────────────────────────────


class QuestionCreate(BaseModel):
    text: str
    options: list[str]
    correct_index: int

    @field_validator("text")
    @classmethod
    def _v_text(cls, v: str) -> str:
        return _validate_question(v)

    @field_validator("options")
    @classmethod
    def _v_options(cls, v: list[str]) -> list[str]:
        return _validate_options(v)

    @model_validator(mode="after")
    def _v_correct(self) -> "QuestionCreate":
        self.correct_index = _validate_correct(self.correct_index, self.options)
        return self


class QuestionUpdate(BaseModel):
    text: str | None = None
    options: list[str] | None = None
    correct_index: int | None = None
    is_active: bool | None = None

    @field_validator("text")
    @classmethod
    def _v_text(cls, v: str | None) -> str | None:
        return _validate_question(v) if v is not None else v

    @field_validator("options")
    @classmethod
    def _v_options(cls, v: list[str] | None) -> list[str] | None:
        return _validate_options(v) if v is not None else v

    @model_validator(mode="after")
    def _v_correct(self) -> "QuestionUpdate":
        if self.options is not None:
            idx = 0 if self.correct_index is None else self.correct_index
            self.correct_index = _validate_correct(idx, self.options)
        return self


# ── Misc endpoints ───────────────────────────────────────────────────────────


class DocxUploadOut(BaseModel):
    """Result of a docx upload: extracted text for the admin to review."""

    text: str
    source_filename: str
    char_count: int


class GenerateOut(BaseModel):
    """Result of AI question generation."""

    generated: int
    skipped: int = 0
    total_questions: int


class PublishOut(BaseModel):
    sent: int
    skipped: int
    total: int
    republished: bool


# ── Results ──────────────────────────────────────────────────────────────────

ResultStatus = Literal["passed", "failed", "in_progress", "not_started"]


class ResultRow(BaseModel):
    user_id: uuid.UUID
    user_name: str
    status: ResultStatus
    attempts: int
    best_score: int | None = None  # percent, only for passed/failed
    passed: bool | None = None
