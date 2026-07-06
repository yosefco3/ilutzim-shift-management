"""
Security-day time validation for the constraint-submission forms.

Guards/admins may not submit a shift that starts before 07:00, and a night
shift may not end later than 07:00 the next morning. Enforced in
``_convert_guard_request`` (the shared guard + admin form path); the constraints
import is intentionally exempt.
"""

import uuid
from datetime import date, time

import pytest

from app.constants import ShiftType
from app.controllers.submission_controller import (
    _convert_guard_request,
    _parse_time,
    _validate_form_window,
)
from app.messages import Messages
from app.schemas.submission_schemas import (
    GuardDayInput,
    GuardShiftInput,
    GuardSubmissionRequest,
)

WEEK_START = date(2026, 7, 5)


def _request(shift_type, from_hour, to_hour):
    return GuardSubmissionRequest(
        week_id=uuid.uuid4(),
        days=[GuardDayInput(
            day_index=0,
            shifts=[GuardShiftInput(
                shift_type=shift_type, from_hour=from_hour, to_hour=to_hour
            )],
        )],
    )


def _convert(shift_type, from_hour, to_hour):
    return _convert_guard_request(_request(shift_type, from_hour, to_hour),
                                  WEEK_START, uuid.uuid4())


class TestValidateFormWindow:
    def test_morning_from_anchor_ok(self):
        _validate_form_window(ShiftType.MORNING, time(7, 0), time(16, 30))

    def test_morning_before_anchor_rejected(self):
        with pytest.raises(ValueError, match=Messages.VAL_SHIFT_BEFORE_ANCHOR):
            _validate_form_window(ShiftType.MORNING, time(6, 30), time(15, 0))

    def test_evening_before_anchor_rejected(self):
        with pytest.raises(ValueError, match=Messages.VAL_SHIFT_BEFORE_ANCHOR):
            _validate_form_window(ShiftType.AFTERNOON, time(6, 0), time(15, 0))

    def test_evening_reversed_rejected(self):
        with pytest.raises(ValueError):
            _validate_form_window(ShiftType.AFTERNOON, time(15, 0), time(8, 0))

    def test_same_start_end_rejected(self):
        """A zero-length morning window (start == end) must be rejected, else
        ``intervals.normalize`` reads it as a full 24h phantom availability."""
        with pytest.raises(ValueError, match=Messages.VAL_SAME_START_END):
            _validate_form_window(ShiftType.MORNING, time(8, 0), time(8, 0))

    def test_night_wraps_to_anchor_ok(self):
        _validate_form_window(ShiftType.NIGHT, time(23, 0), time(7, 0))

    def test_night_no_wrap_ok(self):
        _validate_form_window(ShiftType.NIGHT, time(19, 0), time(23, 0))

    def test_night_past_anchor_rejected(self):
        with pytest.raises(ValueError, match=Messages.VAL_NIGHT_PAST_ANCHOR):
            _validate_form_window(ShiftType.NIGHT, time(23, 0), time(8, 0))

    def test_night_start_before_anchor_rejected(self):
        with pytest.raises(ValueError, match=Messages.VAL_SHIFT_BEFORE_ANCHOR):
            _validate_form_window(ShiftType.NIGHT, time(6, 30), time(7, 0))


class TestConvertGuardRequest:
    def test_valid_morning_converts(self):
        result = _convert(ShiftType.MORNING, "07:00", "16:30")
        assert result.days[0].shifts[0].start_time == time(7, 0)

    def test_early_morning_rejected(self):
        with pytest.raises(ValueError, match=Messages.VAL_SHIFT_BEFORE_ANCHOR):
            _convert(ShiftType.MORNING, "06:30", "15:00")

    def test_night_past_anchor_rejected(self):
        with pytest.raises(ValueError, match=Messages.VAL_NIGHT_PAST_ANCHOR):
            _convert(ShiftType.NIGHT, "23:00", "08:00")

    def test_partial_hours_skipped_not_validated(self):
        """A shift with a missing hour is dropped, never validated/rejected."""
        result = _convert(ShiftType.MORNING, "06:30", "")
        assert result.days[0].is_available is False
        assert result.days[0].shifts == []


class TestParseTime:
    def test_parse_time_out_of_range_rejected(self):
        """Out-of-range input is a form error — reject, don't silently modulo."""
        with pytest.raises(ValueError):
            _parse_time("25:70")
        with pytest.raises(ValueError):
            _parse_time("24:00")

    def test_parse_time_in_range_ok(self):
        assert _parse_time("23:59") == time(23, 59)
        assert _parse_time("07:00") == time(7, 0)
