"""
Question generation via the Claude API.

Admin-only, called once per procedure to build the quiz bank from the procedure
text. Uses the Anthropic SDK's structured-output support (``messages.parse`` with
a Pydantic ``output_format``) so the response parses directly into validated
``{text, options[4], correct_index}`` items.

The API key is INTENTIONALLY optional (see ``Settings.ANTHROPIC_API_KEY``):
steps 1–9 ship dark without it. ``generate`` validates the key at call time and
raises ``GenerationUnavailableException`` (→ 503) when it is missing or the API
fails — no partial state, generation never writes the DB itself.
"""

import logging

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field, ValidationError

from app.config import get_settings
from app.exceptions import AppBaseException
from app.procedures.constants import (
    MAX_OPTION_CHARS,
    MAX_OPTIONS,
    MAX_QUESTION_CHARS,
    MIN_OPTIONS,
)

logger = logging.getLogger("ilutzim")

GENERATE_MAX_TOKENS = 16000


class GenerationUnavailableException(AppBaseException):
    """Raised when question generation cannot run (no key, or API failure).

    Surfaces as HTTP 503 — retryable, not a client error.
    """

    status_code = 503
    message = (
        "שירות יצירת השאלות אינו זמין כעת — מפתח ANTHROPIC_API_KEY לא מוגדר או שגיאת API. "
        "ניתן לנסות שוב מאוחר יותר."
    )


# ── Structured-output schema (sent to Claude as a strict JSON schema) ─────────


class _QuestionItem(BaseModel):
    """One MCQ exactly as Claude must return it."""

    text: str = Field(description="טקסט השאלה, עד 300 תווים")
    options: list[str] = Field(description="בדיוק 4 תשובות אפשריות, כל אחת עד 100 תווים")
    correct_index: int = Field(description="אינדקס התשובה הנכונה (0–3)")


class _QuestionBank(BaseModel):
    """The whole bank Claude returns in one structured response."""

    questions: list[_QuestionItem]


# ── Service ──────────────────────────────────────────────────────────────────


class QuestionGenerationService:
    """Calls Claude once to generate a procedure's MCQ bank."""

    def __init__(self, client_factory=None) -> None:
        # client_factory(api_key) -> AsyncAnthropic-like client. Injected in
        # tests so no network call is made. Defaults to the real SDK client.
        self._client_factory = client_factory

    def _client(self, api_key: str):
        if self._client_factory is not None:
            return self._client_factory(api_key)
        return AsyncAnthropic(api_key=api_key)

    async def generate(self, procedure_text: str, model: str) -> list[dict]:
        """Generate a question bank from ``procedure_text``.

        Returns a list of validated ``{text, options, correct_index}`` dicts
        (options truncated to the Telegram limits). Raises
        ``GenerationUnavailableException`` (503) if the key is missing or the
        API call fails — never returns a partial/garbage bank.
        """
        api_key = get_settings().ANTHROPIC_API_KEY
        if not api_key:
            logger.warning("Question generation requested with no ANTHROPIC_API_KEY")
            raise GenerationUnavailableException()

        prompt = _build_prompt(procedure_text)
        try:
            client = self._client(api_key)
            response = await client.messages.parse(
                model=model,
                max_tokens=GENERATE_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
                output_format=_QuestionBank,
            )
        except GenerationUnavailableException:
            raise
        except Exception as exc:
            logger.error("Claude question generation failed: %s", exc)
            raise GenerationUnavailableException() from exc

        bank = getattr(response, "parsed_output", None)
        if bank is None:
            logger.error("Claude returned no parsed output")
            raise GenerationUnavailableException()

        return _validate_bank(bank)


def _build_prompt(procedure_text: str) -> str:
    """The Hebrew generation prompt (grounded MCQs, Telegram-limit aware)."""
    return (
        "אתה יוצר בנק שאלות אמריקאיות למבחן הבקיאות של צוות אבטחה על נוהל ביטחון (סד\"פ).\n\n"
        "הנוהל:\n"
        f'"""\n{procedure_text}\n"""\n\n'
        "הוראות:\n"
        "- צור בין 15 ל-20 שאלות אמריקאיות המבוססות אך ורק על תוכן הנוהל שלמעלה.\n"
        "- לכל שאלה בדיוק 4 תשובות; רק אחת נכונה.\n"
        f"- טקסט השאלה עד {MAX_QUESTION_CHARS} תווים; כל תשובה עד {MAX_OPTION_CHARS} תווים.\n"
        "- המסיחים צריכים להיות סבירים אך מוטעים בבירור על פי הנוהל.\n"
        "- אל תמציא עובדות שאינן מופיעות בנוהל.\n"
        "- החזר את כל השאלות באובייקט JSON יחיד."
    )


def _validate_bank(bank) -> list[dict]:
    """Coerce the parsed bank into clean, Telegram-safe question dicts.

    Drops any item that fails validation (wrong option count, bad index, or
    empty text) and truncates overlong fields to the poll limits. An empty
    result after validation is treated as a generation failure (503).
    """
    items: list[dict] = []
    try:
        raw_items = bank.questions
    except AttributeError:
        raise GenerationUnavailableException()

    for item in raw_items:
        try:
            options = list(item.options)
            text = (item.text or "").strip()
            correct_index = item.correct_index
        except AttributeError:
            continue

        if not text:
            continue
        if len(options) < MIN_OPTIONS or len(options) > MAX_OPTIONS:
            continue
        if not isinstance(correct_index, int) or correct_index < 0 or correct_index >= len(options):
            continue

        text = text[:MAX_QUESTION_CHARS]
        options = [(o or "").strip()[:MAX_OPTION_CHARS] for o in options]
        if any(not o for o in options):
            continue
        items.append({"text": text, "options": options, "correct_index": correct_index})

    if not items:
        logger.error("Question generation yielded no valid questions")
        raise GenerationUnavailableException()
    return items
