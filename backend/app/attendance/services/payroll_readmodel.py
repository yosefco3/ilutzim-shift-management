"""
Payroll read-model (stage 3 / 03) — the single source both YLM reports render.

One ``EmployeeMonth`` per guard per calendar month: a row for EVERY calendar
day (empty days included — the YLM sheet prints the full month), day letters
א–ש, per-day totals against the planned norm, and month totals. Hours columns
only — the rate columns (100/125/150, Shabbat) stay blank by decision 4/7;
the payroll bureau computes them.

Semantics locked with the sample PDFs (~/Documents/1.pdf, 2.pdf):
- "אתר"  = the planned position name(s) that day.
- "תקן"  = the planned minutes from the built schedule (our planned side).
- "ח/ע"  = actual − planned, negative allowed ("-33:41" style).
- check-in exact; check-out quarter-rounded unless admin-entered (final).
- a day with two shifts prints two rows (like the sample).
"""

import calendar
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date as date_type, datetime, timedelta

from app.attendance.services.attendance_settings import AttendanceConfig
from app.attendance.services.comparison_service import (
    ComparisonService,
    UserDayComparison,
)
from app.repositories.user_repository import UserRepository

logger = logging.getLogger("ilutzim")

HEB_DAY_LETTERS = ["א", "ב", "ג", "ד", "ה", "ו", "ש"]  # Sunday-first


def minutes_hhmm(minutes: int) -> str:
    """Signed minutes → 'H:MM' / '-H:MM' (YLM prints negatives with a dash)."""
    sign = "-" if minutes < 0 else ""
    minutes = abs(int(minutes))
    return f"{sign}{minutes // 60}:{minutes % 60:02d}"


def _day_letter(day: date_type) -> str:
    # Python: Monday=0..Sunday=6 → Sunday-first Hebrew letters.
    return HEB_DAY_LETTERS[(day.weekday() + 1) % 7]


@dataclass(frozen=True)
class MonthRow:
    """One printed line of the per-employee sheet."""

    day: date_type
    day_letter: str
    site: str                     # planned position name(s); "" on empty days
    check_in: datetime | None
    check_out: datetime | None    # the OPERATIVE value (rounded / admin-final)
    check_out_raw: datetime | None
    total_minutes: int            # this row's shift length (operative)
    norm_minutes: int | None      # planned minutes — on the day's FIRST row only
    diff_minutes: int | None      # actual − norm — on the day's first row only
    notes: str = ""
    edited: bool = False          # any manual punch → orange cell in the sheet


@dataclass(frozen=True)
class MonthTotals:
    work_days: int
    actual_minutes: int
    norm_minutes: int
    diff_minutes: int


@dataclass(frozen=True)
class EmployeeMonth:
    user_id: uuid.UUID
    user_name: str
    national_id: str
    payroll_employee_id: str
    payroll_ylm_code: str
    company_name: str
    year: int
    month: int
    rows: list[MonthRow] = field(default_factory=list)
    totals: MonthTotals = None


class PayrollReadModel:
    """Builds EmployeeMonth objects from the comparison layer."""

    def __init__(
        self,
        comparison: ComparisonService,
        users: UserRepository,
        config: AttendanceConfig,
    ) -> None:
        self._comparison = comparison
        self._users = users
        self._config = config

    async def get_month(
        self, user_id: uuid.UUID, year: int, month: int, *, now: datetime
    ) -> EmployeeMonth:
        user = await self._users.get_by_id(user_id)
        first = date_type(year, month, 1)
        last = date_type(year, month, calendar.monthrange(year, month)[1])

        period = await self._comparison.get_user_period(
            user_id, first, last, now=now
        )
        by_day: dict[date_type, UserDayComparison] = {
            d.date: d for d in period["days"]
        }

        rows: list[MonthRow] = []
        work_days = actual_total = norm_total = 0
        day = first
        while day <= last:
            cmp_day = by_day.get(day)
            if cmp_day is None:
                rows.append(
                    MonthRow(
                        day=day, day_letter=_day_letter(day), site="",
                        check_in=None, check_out=None, check_out_raw=None,
                        total_minutes=0, norm_minutes=None, diff_minutes=None,
                    )
                )
            else:
                rows.extend(self._day_rows(cmp_day))
                if cmp_day.actual:
                    work_days += 1
                actual_total += cmp_day.summary.actual_minutes
                norm_total += cmp_day.summary.planned_minutes
            day += timedelta(days=1)

        return EmployeeMonth(
            user_id=user_id,
            user_name=user.full_name if user else "לא ידוע",
            national_id=(user.national_id or "") if user else "",
            payroll_employee_id=(user.payroll_employee_id or "") if user else "",
            payroll_ylm_code=(user.payroll_ylm_code or "") if user else "",
            company_name=self._config.company_name,
            year=year,
            month=month,
            rows=rows,
            totals=MonthTotals(
                work_days=work_days,
                actual_minutes=actual_total,
                norm_minutes=norm_total,
                diff_minutes=actual_total - norm_total,
            ),
        )

    async def get_month_all(
        self, year: int, month: int, *, now: datetime
    ) -> list[EmployeeMonth]:
        """Every active guard's month — the center report's feed. All months
        share one comparison service, so the week cache is reused across users."""
        out = []
        for user in await self._users.get_active_users():
            out.append(await self.get_month(user.id, year, month, now=now))
        out.sort(key=lambda m: m.user_name)
        return out

    def _day_rows(self, cmp_day: UserDayComparison) -> list[MonthRow]:
        site = " / ".join(dict.fromkeys(w.position_name for w in cmp_day.planned))
        summary = cmp_day.summary
        letter = _day_letter(cmp_day.date)

        if not cmp_day.actual:
            # scheduled but nobody punched (no-show / approved absence)
            note = "היעדרות מאושרת" if summary.tag == "היעדרות מאושרת ✎" else ""
            return [
                MonthRow(
                    day=cmp_day.date, day_letter=letter, site=site,
                    check_in=None, check_out=None, check_out_raw=None,
                    total_minutes=0,
                    norm_minutes=summary.planned_minutes,
                    diff_minutes=-summary.planned_minutes,
                    notes=note,
                )
            ]

        rows = []
        for idx, actual in enumerate(cmp_day.actual):
            operative_out = actual.check_out_rounded
            total = 0
            if operative_out is not None:
                total = max(
                    0, int((operative_out - actual.check_in_at).total_seconds() // 60)
                )
            notes = []
            if (
                actual.check_out_raw is not None
                and operative_out is not None
                and operative_out != actual.check_out_raw
            ):
                notes.append(
                    f"יציאה בפועל {actual.check_out_raw.strftime('%H:%M')}"
                )
            edited = "manual" in (actual.in_source, actual.out_source)
            if edited:
                notes.append("הוזן/תוקן ידנית")
            if actual.check_out_raw is None:
                notes.append("חסרה יציאה")
            if idx == 0 and summary.orphan_out_times:
                notes.append(
                    "יציאה בלי כניסה " + ", ".join(summary.orphan_out_times)
                )
            rows.append(
                MonthRow(
                    day=cmp_day.date, day_letter=letter, site=site,
                    check_in=actual.check_in_at,
                    check_out=operative_out,
                    check_out_raw=actual.check_out_raw,
                    total_minutes=total,
                    norm_minutes=summary.planned_minutes if idx == 0 else None,
                    diff_minutes=(
                        summary.actual_minutes - summary.planned_minutes
                        if idx == 0 else None
                    ),
                    notes=" · ".join(notes),
                    edited=edited,
                )
            )
        return rows
