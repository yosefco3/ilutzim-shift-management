"""
Attendance admin endpoints (stage 3 / 02).

Registered in ``main.py`` only when ``ATTENDANCE_ENABLED`` is on, so with the
flag off every path here returns 404. Read-only in this step — the edit /
manual-entry endpoints arrive with the adjustments layer.
"""

import logging
import uuid
from datetime import date as date_type, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.attendance.constants import AdjustmentAction, PunchDirection
from app.attendance.dependencies import (
    get_adjustment_service,
    get_comparison_service,
    get_event_repo,
    get_payroll_readmodel,
)
from app.attendance.repositories.event_repository import AttendanceEventRepository
from app.attendance.schemas import (
    AdjustmentOut,
    AdjustmentRequest,
    AdjustmentResult,
    BandOut,
    DayViewOut,
    ManualEntryRequest,
    PeriodSummaryRow,
    StatusOut,
    UserDayOut,
    UserPeriodOut,
)
from app.attendance.services.adjustment_service import AdjustmentService
from app.exceptions import ValidationException
from app.attendance.services.comparison_service import (
    BAND_EVENING,
    BAND_MORNING,
    BAND_NIGHT,
    ComparisonService,
)
from app.dependencies import require_admin_role
from app.utils.date_utils import now_il, today_il

logger = logging.getLogger("ilutzim")

router = APIRouter(
    prefix="/admin/attendance",
    tags=["Admin – Attendance"],
    dependencies=[Depends(require_admin_role)],
)

MAX_PERIOD_DAYS = 62  # a bit over two months — the UI asks for week or month

_BAND_ORDER = [BAND_MORNING, BAND_EVENING, BAND_NIGHT]


def _now() -> datetime:
    return now_il().replace(tzinfo=None)


@router.get("/ping")
async def ping() -> dict[str, bool]:
    """Wiring check — proves the feature-flagged router is registered."""
    return {"enabled": True}


@router.get("/status", response_model=StatusOut)
async def status(
    events: AttendanceEventRepository = Depends(get_event_repo),
) -> StatusOut:
    """Source-health widget for the attendance page header."""
    now = _now()
    day_start = datetime.combine(now.date(), time.min)
    return StatusOut(
        enabled=True,
        events_today=await events.count_since(day_start),
        last_event_at=await events.last_event_at(),
    )


@router.get("/day", response_model=DayViewOut)
async def day_view(
    date: date_type | None = Query(default=None),
    service: ComparisonService = Depends(get_comparison_service),
) -> DayViewOut:
    """All relevant employees for one day, classified and grouped by band."""
    day = date or today_il()
    data = await service.get_day_all(day, now=_now())
    rows = [UserDayOut.model_validate(r) for r in data["rows"]]
    bands = [
        BandOut(band=band, rows=[r for r in rows if r.band == band])
        for band in _BAND_ORDER
    ]
    return DayViewOut(
        date=data["date"],
        now=data["now"],
        counters=data["counters"],
        bands=[b for b in bands if b.rows],
    )


@router.post("/adjustments", response_model=AdjustmentResult)
async def create_adjustment(
    body: AdjustmentRequest,
    service: AdjustmentService = Depends(get_adjustment_service),
    comparison: ComparisonService = Depends(get_comparison_service),
) -> AdjustmentResult:
    """Apply one admin correction and return the refreshed day."""
    now = _now()
    try:
        action = AdjustmentAction(body.action)
    except ValueError:
        raise HTTPException(status_code=422, detail="פעולה לא מוכרת")

    try:
        if action == AdjustmentAction.EDIT_TIME:
            if body.event_id is None or body.punched_at is None:
                raise ValidationException("חסרים שדות: event_id, punched_at")
            adjustment = await service.edit_time(
                body.event_id, body.punched_at, body.reason, now=now
            )
        elif action == AdjustmentAction.ADD_PUNCH:
            if body.user_id is None or body.punched_at is None or body.direction is None:
                raise ValidationException("חסרים שדות: user_id, direction, punched_at")
            adjustment = await service.add_punch(
                body.user_id,
                PunchDirection(body.direction),
                body.punched_at,
                body.reason,
                now=now,
            )
        elif action == AdjustmentAction.VOID_PUNCH:
            if body.event_id is None:
                raise ValidationException("חסר שדה: event_id")
            adjustment = await service.void_punch(body.event_id, body.reason)
        else:  # MARK_ABSENCE
            if body.user_id is None or body.work_date is None:
                raise ValidationException("חסרים שדות: user_id, work_date")
            adjustment = await service.mark_absence(
                body.user_id, body.work_date, body.reason
            )
    except ValidationException as exc:
        raise HTTPException(status_code=422, detail=exc.message)

    day = await comparison.get_user_day(
        adjustment.user_id, adjustment.work_date, now=now
    )
    return AdjustmentResult(
        adjustment=AdjustmentOut.model_validate(adjustment),
        day=UserDayOut.model_validate(day),
    )


@router.post("/manual-entry", response_model=UserDayOut)
async def manual_entry(
    body: ManualEntryRequest,
    service: AdjustmentService = Depends(get_adjustment_service),
    comparison: ComparisonService = Depends(get_comparison_service),
) -> UserDayOut:
    """Quick full-day manual attendance (guards without Telegram): one call
    records IN (+optional OUT) with audit, and returns the refreshed day."""
    now = _now()
    try:
        check_in = datetime.combine(body.date, _parse_hhmm_strict(body.check_in))
        adjustment = await service.add_punch(
            body.user_id, PunchDirection.IN, check_in, body.reason, now=now
        )
        if body.check_out:
            check_out = datetime.combine(
                body.date, _parse_hhmm_strict(body.check_out)
            )
            if check_out <= check_in:  # night shift crossing midnight
                check_out += timedelta(days=1)
            await service.add_punch(
                body.user_id, PunchDirection.OUT, check_out, body.reason, now=now
            )
    except ValidationException as exc:
        raise HTTPException(status_code=422, detail=exc.message)

    day = await comparison.get_user_day(body.user_id, adjustment.work_date, now=now)
    return UserDayOut.model_validate(day)


def _parse_hhmm_strict(value: str):
    from datetime import time as time_type

    try:
        h, m = value.strip().split(":")
        return time_type(int(h), int(m))
    except (ValueError, AttributeError):
        raise ValidationException("שעה לא תקינה (HH:MM)")


def _validate_month(year: int, month: int) -> None:
    if not (2020 <= year <= 2100) or not (1 <= month <= 12):
        raise HTTPException(status_code=422, detail="חודש/שנה לא תקינים")


@router.get("/export/employee/{user_id}")
async def export_employee_report(
    user_id: uuid.UUID,
    year: int = Query(),
    month: int = Query(),
    readmodel=Depends(get_payroll_readmodel),
):
    """The YLM per-employee monthly attendance sheet (hours columns only)."""
    from fastapi.responses import StreamingResponse

    from app.attendance.services.ylm_export_service import YlmExportService

    _validate_month(year, month)
    employee_month = await readmodel.get_month(user_id, year, month, now=_now())
    data = YlmExportService().export_employee_report(employee_month)
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename=ylm_employee_{year}-{month:02d}_{user_id}.xlsx"
            )
        },
    )


@router.get("/export/center")
async def export_center_report(
    year: int = Query(),
    month: int = Query(),
    readmodel=Depends(get_payroll_readmodel),
):
    """The YLM center sheet — one summary line per active employee."""
    from fastapi.responses import StreamingResponse

    from app.attendance.services.ylm_export_service import YlmExportService

    _validate_month(year, month)
    months = await readmodel.get_month_all(year, month, now=_now())
    company = months[0].company_name if months else ""
    data = YlmExportService().export_center_report(months, year, month, company)
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename=ylm_center_{year}-{month:02d}.xlsx"
            )
        },
    )


@router.get("/adjustments", response_model=list[AdjustmentOut])
async def adjustment_history(
    user_id: uuid.UUID = Query(),
    work_date: date_type = Query(),
    service: AdjustmentService = Depends(get_adjustment_service),
) -> list[AdjustmentOut]:
    """The audit trail for one user-day (tooltip / history view)."""
    rows = await service.history(user_id, work_date)
    return [AdjustmentOut.model_validate(r) for r in rows]


@router.get("/period-summary", response_model=list[PeriodSummaryRow])
async def period_summary(
    date_from: date_type = Query(alias="from"),
    date_to: date_type = Query(alias="to"),
    service: ComparisonService = Depends(get_comparison_service),
) -> list[PeriodSummaryRow]:
    """Aggregated per-employee lines for the week/month list view."""
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="טווח תאריכים הפוך")
    if (date_to - date_from) > timedelta(days=MAX_PERIOD_DAYS):
        raise HTTPException(
            status_code=422, detail=f"טווח מוגבל ל-{MAX_PERIOD_DAYS} ימים"
        )
    rows = await service.get_period_summary(date_from, date_to, now=_now())
    return [PeriodSummaryRow(**r) for r in rows]


@router.get("/users/{user_id}", response_model=UserPeriodOut)
async def user_period(
    user_id: uuid.UUID,
    date_from: date_type = Query(alias="from"),
    date_to: date_type = Query(alias="to"),
    service: ComparisonService = Depends(get_comparison_service),
) -> UserPeriodOut:
    """One employee's classified days over a week/month range."""
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="טווח תאריכים הפוך")
    if (date_to - date_from) > timedelta(days=MAX_PERIOD_DAYS):
        raise HTTPException(
            status_code=422, detail=f"טווח מוגבל ל-{MAX_PERIOD_DAYS} ימים"
        )
    data = await service.get_user_period(user_id, date_from, date_to, now=_now())
    return UserPeriodOut(
        user_id=data["user_id"],
        user_name=data["user_name"],
        date_from=data["from"],
        date_to=data["to"],
        days=[UserDayOut.model_validate(d) for d in data["days"]],
        summary=data["summary"],
    )
