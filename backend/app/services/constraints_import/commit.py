"""Commit a parsed constraints import into the existing availability model.

Writes each guard's availability into ``WeeklySubmission`` / ``DailyStatus`` /
``ShiftWindow`` — the **same** model Telegram submissions use — so the schedule
builder reads from one source of truth.

Locked rules honoured here (see ``STAGE_B_PROMPTS/README.md``):

* **Identity = id-then-name, find-or-create.** If the file carries the guard's
  DB id (the ``מזהה`` column written by the export), match on it first — robust
  to renames; otherwise fall back to full name. If neither matches, create one
  (no attributes by default, active). No rejection, no duplicate handling.
* **Target week = the week in the file title.** Find the week whose
  ``start_date``/``end_date`` match the parsed range; never create one silently.
  A ``week_id`` override is accepted for manual selection.
* **Upsert, like Telegram.** Re-import updates in place (no duplicates) via
  ``submission_service.create_submission(..., override_lock=True)``.
* Windows are stored **as-is** (not merged — merging is a display/builder
  concern). ``זמין`` (ALL_DAY) is stored as the shift's default window
  (see ``hours.DEFAULT_SHIFT_WINDOWS``); empty/``לא זמין`` → no window and the
  day is marked unavailable when it has no windows at all.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import time, timedelta

from app.constants import ShiftType
from app.models.user import User
from app.schemas.constraints_import import (
    ConstraintsCommitResponse,
    ImportSummary,
)
from app.schemas.submission_schemas import (
    DayStatusInput,
    ShiftWindowInput,
    SubmissionCreate,
)

from .hours import DEFAULT_SHIFT_WINDOWS
from .parser import CellKind, ParsedGuard, ParsedImport
from .preview import build_preview

logger = logging.getLogger("ilutzim")

_SHIFT_ORDER = (ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT)


class WeekNotFoundError(ValueError):
    """Raised when the import's target week does not exist (no silent create)."""


def _normalize_phone(raw: str | None) -> str:
    """Best-effort phone normalisation; fall back to a unique placeholder.

    Phone is not used by the scheduler, but the model column is required and
    unique — so a guard without a valid phone still gets a collision-free value.
    """
    if raw:
        cleaned = raw.replace(" ", "").replace("-", "").lstrip("+")
        if re.match(r"^05\d{8}$", cleaned):
            return "972" + cleaned[1:]
        if re.match(r"^972\d{9}$", cleaned):
            return cleaned
    return f"ייבוא-{uuid.uuid4().hex[:8]}"


def _split_name(name: str) -> tuple[str, str]:
    parts = name.split()
    if not parts:
        return name, ""
    return parts[0], " ".join(parts[1:])


def _build_days(
    guard: ParsedGuard,
    week_start,
    default_windows: dict[ShiftType, tuple[time, time]],
) -> list[DayStatusInput]:
    """Map a guard's 7×shift cells into per-day submission inputs (windows as-is)."""
    days: list[DayStatusInput] = []
    for day_index in range(7):
        day_date = week_start + timedelta(days=day_index)
        cells = guard.cells.get(day_index, {})
        shifts: list[ShiftWindowInput] = []
        for shift_type in _SHIFT_ORDER:
            cell = cells.get(shift_type)
            if cell is None or cell.kind == CellKind.UNAVAILABLE:
                continue
            if cell.kind == CellKind.WINDOW and cell.start and cell.end:
                shifts.append(
                    ShiftWindowInput(
                        shift_type=shift_type,
                        start_time=cell.start,
                        end_time=cell.end,
                    )
                )
            elif cell.kind == CellKind.ALL_DAY:
                start, end = default_windows[shift_type]
                shifts.append(
                    ShiftWindowInput(
                        shift_type=shift_type, start_time=start, end_time=end
                    )
                )
        days.append(
            DayStatusInput(
                date=day_date,
                is_available=bool(shifts),
                shifts=shifts,
            )
        )
    return days


class ConstraintsCommitService:
    """Persist a ``ParsedImport`` into the availability model (find-or-create)."""

    def __init__(self, user_repo, week_repo, submission_service) -> None:
        self._user_repo = user_repo
        self._week_repo = week_repo
        self._submission_service = submission_service

    async def _resolve_week(self, parsed: ParsedImport, week_id: uuid.UUID | None):
        if week_id is not None:
            week = await self._week_repo.get_by_id(week_id)
            if week is None:
                raise WeekNotFoundError("השבוע שנבחר לא נמצא")
            return week
        if parsed.week_start is None or parsed.week_end is None:
            raise WeekNotFoundError(
                "לא ניתן לזהות את שבוע היעד מכותרת הקובץ — בחר שבוע ידנית"
            )
        week = await self._week_repo.get_by_date_range(
            parsed.week_start, parsed.week_end
        )
        if week is None:
            raise WeekNotFoundError(
                f"לא קיים שבוע התואם לטווח {parsed.week_start}–{parsed.week_end}. "
                "צור את השבוע תחילה או בחר שבוע ידנית."
            )
        return week

    async def _find_or_create_user(
        self,
        guard: ParsedGuard,
        name_map: dict[str, User],
        id_map: dict[str, User],
    ) -> tuple[User, bool]:
        # Prefer matching by the DB id carried in the file (robust to renames);
        # fall back to full-name identity, then find-or-create.
        if guard.guard_id and guard.guard_id in id_map:
            return id_map[guard.guard_id], False
        existing = name_map.get(guard.name)
        if existing is not None:
            return existing, False
        first, last = _split_name(guard.name)
        user = User(
            phone_number=_normalize_phone(guard.phone),
            first_name=first,
            last_name=last,
            roles=list(guard.roles),
            is_active=True,
        )
        created = await self._user_repo.save(user)
        name_map[guard.name] = created
        id_map[str(created.id)] = created
        return created, True

    async def commit(
        self,
        parsed: ParsedImport,
        *,
        week_id: uuid.UUID | None = None,
        default_windows: dict[ShiftType, tuple[time, time]] | None = None,
    ) -> ConstraintsCommitResponse:
        windows = default_windows or DEFAULT_SHIFT_WINDOWS
        week = await self._resolve_week(parsed, week_id)

        all_users = await self._user_repo.get_all_users()
        name_map: dict[str, User] = {u.full_name: u for u in all_users}
        id_map: dict[str, User] = {str(u.id): u for u in all_users}
        existing_names = set(name_map.keys())
        existing_ids = set(id_map.keys())

        errors: list[str] = list(parsed.errors)
        imported = 0
        created_new = 0

        for guard in parsed.guards:
            try:
                user, was_created = await self._find_or_create_user(
                    guard, name_map, id_map
                )
                if was_created:
                    created_new += 1
                elif guard.roles:
                    # Keep an existing guard's structured attributes in sync with
                    # what the import carried (union — never drop manual roles).
                    new_roles = [r for r in guard.roles if r not in (user.roles or [])]
                    if new_roles:
                        user.roles = list(user.roles or []) + new_roles
                        await self._user_repo.save(user)

                data = SubmissionCreate(
                    week_id=week.id,
                    user_id=user.id,
                    general_notes=guard.notes,
                    days=_build_days(guard, week.start_date, windows),
                )
                await self._submission_service.create_submission(
                    data, override_lock=True
                )
                imported += 1
            except Exception as exc:  # per-guard failure must not abort the batch
                logger.warning("constraints commit failed for %s: %s", guard.name, exc)
                errors.append(f"{guard.name}: שמירה נכשלה ({exc})")

        summary = ImportSummary(
            week_start=parsed.week_start,
            week_end=parsed.week_end,
            imported=imported,
            created_new=created_new,
            errors=errors,
        )
        preview = build_preview(parsed, existing_names, existing_ids)
        return ConstraintsCommitResponse(summary=summary, guards=preview.guards)
